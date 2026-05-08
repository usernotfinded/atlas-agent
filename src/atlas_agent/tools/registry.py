import inspect
from typing import Any, Dict, List, Union

from atlas_agent.core.types import Session, UserApprovalPending
from atlas_agent.tools.spec import (
    GuardrailChain,
    ModelCapabilities,
    ToolCall,
    ToolDescription,
    ToolError,
    ToolResult,
    ToolSpec,
)

CONTEXT_WINDOW_FULL_DESC_THRESHOLD = 128_000

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self.enabled_tools_config: Dict[str, bool] = {}  # Optional overrides from tools.yaml

    def _validate_signature(self, tool: ToolSpec) -> None:
        """
        Validates that the execute callable's signature is compatible with the input_schema.
        """
        sig = inspect.signature(tool.execute)
        params = sig.parameters
        
        properties = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])

        # Check that required properties are in the parameters
        for req in required:
            if req not in params:
                # If there is a **kwargs parameter, it's technically allowed
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                if not has_kwargs:
                    raise ValueError(f"Required schema property '{req}' is missing from callable signature.")

        # Check that non-kwargs parameters are in the schema
        for name, param in params.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name == "session":
                # Injecting session is handled specifically if needed, but standard tools might not take it directly
                # If it's a domain tool it might just take arguments.
                # In many agent frameworks, session is passed if requested. We'll ignore `session` for schema matching.
                continue
            if name not in properties and param.default == inspect.Parameter.empty:
                 raise ValueError(f"Callable parameter '{name}' without default is not defined in input_schema.")

    def register(self, tool: ToolSpec) -> None:
        self._validate_signature(tool)
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry.")
        return self._tools[name]

    def list_tools(self, enabled_only: bool = True) -> List[ToolSpec]:
        tools = list(self._tools.values())
        if not enabled_only:
            return tools
            
        result = []
        for tool in tools:
            # Check override first, then fallback to default
            is_enabled = self.enabled_tools_config.get(tool.name, tool.default_enabled)
            if is_enabled:
                result.append(tool)
        return result

    def describe_for_model(self, model_capabilities: ModelCapabilities) -> List[ToolDescription]:
        tools = self.list_tools(enabled_only=True)
        descriptions = []
        
        use_full_desc = model_capabilities.context_window >= CONTEXT_WINDOW_FULL_DESC_THRESHOLD
        
        for tool in tools:
            desc_text = tool.description_full if use_full_desc else tool.description_compact
            descriptions.append(
                ToolDescription(
                    name=tool.name,
                    description=desc_text,
                    schema_dict=tool.input_schema,
                )
            )
        return descriptions

    def execute(
        self,
        tool_call: ToolCall,
        guardrails: GuardrailChain,
        session: Session,
    ) -> Union[ToolResult, ToolError, UserApprovalPending]:
        try:
            tool = self.get_tool(tool_call.name)
        except KeyError:
            return ToolError(
                error_type="not_found",
                message=f"Tool '{tool_call.name}' is not registered.",
                is_retryable=False,
                suggested_action="Use a different tool.",
            )

        # Check if enabled
        is_enabled = self.enabled_tools_config.get(tool.name, tool.default_enabled)
        if not is_enabled:
            return ToolError(
                error_type="unavailable",
                message=f"Tool '{tool_call.name}' is disabled.",
                is_retryable=False,
                suggested_action="Tool is currently disabled by configuration.",
            )

        # Guardrail chain evaluation
        guardrail_result = guardrails.evaluate(tool_call, session)
        if guardrail_result is not None:
            if isinstance(guardrail_result, ToolError):
                return guardrail_result
            # If the guardrail returns ToolResult or UserApprovalPending directly
            return guardrail_result

        # Execute
        try:
            # Match kwargs with signature
            sig = inspect.signature(tool.execute)
            kwargs = tool_call.arguments.copy()
            if "session" in sig.parameters:
                kwargs["session"] = session
                
            res = tool.execute(**kwargs)
            return ToolResult(data=res, error=False)
            
        except Exception as e:
            return ToolError(
                error_type="broker_error",  # Broad fallback
                message=str(e),
                is_retryable=True,
                suggested_action="Check arguments and try again.",
            )
