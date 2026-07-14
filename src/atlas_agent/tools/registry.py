# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tools/registry.py
# PURPOSE: The set of tools an LLM is allowed to call, and the gate every call goes
#          through. An unregistered tool cannot be invoked, so this registry defines
#          the outer bound of what the model can DO.
# DEPS:    tools.spec (contracts + guardrails), core.types (Session, approval)
# ==============================================================================

# --- IMPORTS ---
import inspect
import time
import logging
from collections import deque
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


# --- CONFIGURATIONS & CONSTANTS ---

# Below this context size, tool descriptions are sent in an abbreviated form. A small
# model would otherwise spend most of its window reading about tools rather than the
# market.
CONTEXT_WINDOW_FULL_DESC_THRESHOLD = 128_000


# ==============================================================================
# TOOL REGISTRY
# ==============================================================================

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self.enabled_tools_config: Dict[str, bool] = {}  # Optional overrides from tools.yaml
        # Per-tool call timestamps, backing the rate limiter. A model stuck in a loop
        # calling the same tool would otherwise hammer whatever is behind it.
        self._rate_limits: Dict[str, deque] = {}

    # --- Registration-time validation ---

    def _validate_signature(self, tool: ToolSpec) -> None:
        """
        Validates that the execute callable's signature is compatible with the input_schema.
        """
        # Checked at REGISTRATION, not at call time. The schema is what the model is
        # shown; the signature is what actually runs. A mismatch between them means the
        # model would be invited to call something that cannot accept its arguments —
        # and that failure must surface at startup, not mid-trade.
        sig = inspect.signature(tool.execute)
        params = sig.parameters
        
        properties = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])

        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if has_kwargs:
            logging.warning(f"Tool {tool.name} uses VAR_KEYWORD; signature validation skipped for non-required params.")

        # Check that required properties are in the parameters
        for req in required:
            if req not in params:
                if not has_kwargs:
                    raise ValueError(f"Required schema property '{req}' is missing from callable signature.")

        # Check that non-kwargs parameters are in the schema
        for name, param in params.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name == "session":
                continue
            if name not in properties and param.default == inspect.Parameter.empty:
                 raise ValueError(f"Callable parameter '{name}' without default is not defined in input_schema.")

    def register(self, tool: ToolSpec) -> None:
        self._validate_signature(tool)
        self._tools[tool.name] = tool
        self._rate_limits[tool.name] = deque()

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
                message=f"Tool '{tool_call.name}' is disabled by configuration.",
                is_retryable=False,
                suggested_action="Tool is currently disabled by configuration.",
            )
            
        # Enforce rate limit
        if tool.rate_limit:
            now = time.time()
            calls = self._rate_limits[tool.name]
            while calls and calls[0] < now - 60:
                calls.popleft()
            if len(calls) >= tool.rate_limit.calls_per_minute:
                return ToolError(
                    error_type="unavailable",
                    message=f"Rate limit exceeded for tool {tool.name}, retry after 60 seconds",
                    is_retryable=True,
                    suggested_action="Wait before calling this tool again.",
                )
            calls.append(now)

        # Validate arguments against schema
        import jsonschema
        try:
            jsonschema.validate(instance=tool_call.arguments, schema=tool.input_schema)
        except jsonschema.exceptions.ValidationError as e:
            return ToolError(
                error_type="validation",
                message=f"Schema validation failed: {e.message}",
                is_retryable=False,
                suggested_action="Fix the arguments to match the tool schema.",
            )

        # Guardrail chain evaluation
        guardrail_result = guardrails.evaluate(tool_call, session)
        if guardrail_result is not None:
            if isinstance(guardrail_result, ToolError):
                return guardrail_result
            return guardrail_result

        # Execute
        try:
            sig = inspect.signature(tool.execute)
            kwargs = tool_call.arguments.copy()
            if "session" in sig.parameters:
                kwargs["session"] = session
                
            res = tool.execute(**kwargs)
            return ToolResult(data=res, error=False)
            
        except Exception as e:
            return ToolError(
                error_type="internal_error",
                message=str(e),
                is_retryable=False,
                suggested_action="Tool implementation error; do not retry, surface to user",
            )