import inspect
from datetime import date
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, Optional, Union, get_type_hints, get_origin, get_args
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
    data: Any
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
        "internal_error",
    ]
    message: str
    is_retryable: bool
    suggested_action: str
    attempt_count: int = 1
    original_payload: Optional[dict] = None

class ModelCapabilities(BaseModel):
    """Internal type used by the registry to evaluate model context limits."""
    context_window: int
    supports_native_tools: bool
    supports_json_mode: bool = False
    supports_streaming: bool = False
    provider_name: str = "unknown"
    model_name: Optional[str] = None

class ToolDescription(BaseModel):
    """Internal type used by the registry to describe tools to the model."""
    name: str
    description: str
    schema_dict: dict

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict
    raw: Optional[dict] = None


class TokenUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class LLMResponse(BaseModel):
    text: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    is_final: bool = True
    usage: Optional[TokenUsage] = None
    raw: Optional[dict] = None

class GuardrailChain(Protocol):
    def evaluate(self, tool_call: ToolCall, session: Any) -> Union[ToolResult, ToolError, None]:
        """
        Evaluate the tool call against the guardrail chain.
        Returns a ToolError if rejected, ToolResult if it handles the execution entirely,
        or None to proceed to normal tool execution.
        """
        ...


class EmptyGuardrailChain:
    def evaluate(self, tool_call: ToolCall, session: Any) -> Union[ToolResult, ToolError, None]:
        return None


def _type_to_schema(t: Any) -> dict:
    """Recursively convert a Python type annotation into a JSON Schema fragment."""
    origin = get_origin(t)
    args = get_args(t)

    # Optional / Union[..., None]
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            return {"anyOf": [_type_to_schema(non_none[0]), {"type": "null"}]}
        return {"anyOf": [_type_to_schema(a) for a in non_none]}

    # list[T]
    if origin is list:
        item_type = args[0] if args else Any
        return {"type": "array", "items": _type_to_schema(item_type)}

    # Literal[...]
    if origin is Literal:
        if args and isinstance(args[0], str):
            return {"type": "string", "enum": list(args)}
        elif args and isinstance(args[0], bool):
            return {"type": "boolean", "enum": list(args)}
        elif args and isinstance(args[0], int):
            return {"type": "integer", "enum": list(args)}
        elif args and isinstance(args[0], float):
            return {"type": "number", "enum": list(args)}
        return {"enum": list(args)}

    # Pydantic BaseModel -> recursive object schema
    if isinstance(t, type) and issubclass(t, BaseModel):
        return _pydantic_model_to_schema(t)

    # Primitive / other types
    if t is str or t is date or t is Path:
        return {"type": "string"}
    if t is int:
        return {"type": "integer"}
    if t is float:
        return {"type": "number"}
    if t is bool:
        return {"type": "boolean"}
    if t is dict:
        return {"type": "object"}
    if t is list:
        return {"type": "array"}

    return {}


def _pydantic_model_to_schema(model_cls: type[BaseModel]) -> dict:
    """Generate a JSON Schema object for a Pydantic BaseModel."""
    schema: dict = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    hints = get_type_hints(model_cls)
    for name, field_info in model_cls.model_fields.items():
        field_type = hints.get(name, Any)
        schema["properties"][name] = _type_to_schema(field_type)
        if field_info.is_required():
            schema["required"].append(name)
    return schema


def generate_input_schema(func: Callable[..., Any]) -> dict:
    """Generate a JSON Schema (input_schema) from a Python callable's signature."""
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        # Skip injected / meta parameters
        if name in ("session", "self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        t = hints.get(name, Any)
        properties[name] = _type_to_schema(t)

        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
