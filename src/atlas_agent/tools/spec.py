from typing import Any, Callable, Literal, Protocol, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

class RateLimit(BaseModel):
    calls_per_minute: int

class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    description_full: str
    description_compact: str
    input_schema: dict
    execute: Callable[..., Any]
    risk_gated: bool = False
    approval_gated: bool = False
    audit_logged: bool = True
    rate_limit: Optional[RateLimit] = None
    default_enabled: bool = True

class ToolResult(BaseModel):
    data: Union[dict, str]
    error: bool = False

class ToolError(BaseModel):
    error_type: Literal[
        "validation",
        "risk_rejected",
        "approval_denied",
        "broker_error",
        "timeout",
        "not_found",
        "unavailable",
        "sandbox_blocked",
    ]
    message: str
    is_retryable: bool
    suggested_action: str
    attempt_count: int = 1
    original_payload: Optional[dict] = None

class ModelCapabilities(BaseModel):
    context_window: int
    supports_native_tools: bool

class ToolDescription(BaseModel):
    name: str
    description: str
    schema_dict: dict

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict
    raw: Optional[dict] = None

class GuardrailChain(Protocol):
    def evaluate(self, tool_call: ToolCall, session: Any) -> Union[ToolResult, ToolError, None]:
        """
        Evaluate the tool call against the guardrail chain.
        Returns a ToolError if rejected, ToolResult if it handles the execution entirely,
        or None to proceed to normal tool execution.
        """
        ...
