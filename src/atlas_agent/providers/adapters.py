# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/adapters.py
# PURPOSE: Normalises every vendor's response shape into one LLMResponse. This is
#          the layer that absorbs the fact that OpenAI, Anthropic and JSON-only
#          models each report tool calls differently — so nothing downstream has to.
# DEPS:    jsonschema (tool-argument validation), tools.spec (the target shape)
#
# DESIGN:  Written defensively throughout. A provider response is UNTRUSTED input:
#          the API may change under us, a proxy may mangle it, a local model may
#          emit something almost-but-not-quite valid. Every accessor tolerates a
#          missing or wrongly-typed field rather than raising deep in a parse.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

from atlas_agent.tools.spec import LLMResponse, TokenUsage, ToolCall, ToolDescription


# --- CONFIGURATIONS & CONSTANTS ---

# Models routinely wrap JSON in a markdown fence despite being told not to. Stripping
# it here is cheaper than losing an otherwise valid decision to a formatting quirk.
_FENCED_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


# ==============================================================================
# DEFENSIVE ACCESSORS
# ==============================================================================

def _value(source: Any, key: str, default: Any = None) -> Any:
    # Handles both dicts and objects, because SDKs disagree: some return parsed JSON,
    # others return typed model objects. Callers should not have to care which.
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _to_raw_dict(value: Any) -> dict[str, Any]:
    # Tries every known way an SDK might expose its payload — plain dict, pydantic
    # model_dump(), legacy .dict(), then __dict__ — and falls back to a stringified
    # value rather than raising. This output is destined for the audit log, and losing
    # the whole record because a vendor changed its object type would be a poor trade.
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "__dict__"):
        dumped = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        if dumped:
            return dumped
    return {"value": str(value)}


def _token_usage_from_raw(raw_usage: Any) -> TokenUsage | None:
    if not isinstance(raw_usage, dict):
        return None
    return TokenUsage(
        prompt_tokens=raw_usage.get("prompt_tokens"),
        completion_tokens=raw_usage.get("completion_tokens"),
        total_tokens=raw_usage.get("total_tokens"),
    )


def _tool_error_like_diagnostic(
    *,
    error_type: str,
    message: str,
    original_payload: dict | None = None,
    is_retryable: bool = False,
) -> dict[str, Any]:
    return {
        "error_type": error_type,
        "message": message,
        "is_retryable": is_retryable,
        "suggested_action": "Return a valid tool call payload.",
        "attempt_count": 1,
        "original_payload": original_payload,
    }


def _with_diagnostic(raw: Any, diagnostic: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        merged = dict(raw)
    else:
        merged = {"raw_response": raw}
    merged["diagnostic"] = diagnostic
    return merged


def _extract_openai_message_text(content: Any) -> str | None:
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                elif isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str) and value.strip():
                        parts.append(value.strip())
        joined = "\n".join(parts).strip()
        return joined or None
    return None


class OpenAICompatibleAdapter:
    @staticmethod
    def normalize(raw: Any) -> LLMResponse:
        choices = _value(raw, "choices", []) or []
        message = {}
        if choices:
            message = _value(choices[0], "message", {}) or {}

        text = _extract_openai_message_text(_value(message, "content"))
        tool_calls_payload = _value(message, "tool_calls", []) if message is not None else []

        diagnostics: list[dict[str, Any]] = []
        normalized_calls: list[ToolCall] = []
        if isinstance(tool_calls_payload, list):
            for idx, tool_call in enumerate(tool_calls_payload, start=1):
                if tool_call is None:
                    diagnostics.append(
                        _tool_error_like_diagnostic(
                            error_type="validation",
                            message="OpenAI tool call must be an object.",
                        )
                    )
                    continue

                function_payload = _value(tool_call, "function")
                if function_payload is None:
                    diagnostics.append(
                        _tool_error_like_diagnostic(
                            error_type="validation",
                            message="OpenAI tool call missing function payload.",
                            original_payload=_to_raw_dict(tool_call),
                        )
                    )
                    continue

                name = _value(function_payload, "name")
                if not isinstance(name, str) or not name.strip():
                    diagnostics.append(
                        _tool_error_like_diagnostic(
                            error_type="validation",
                            message="OpenAI tool call missing function name.",
                            original_payload=_to_raw_dict(tool_call),
                        )
                    )
                    continue

                arguments_payload = _value(function_payload, "arguments", {})
                arguments: dict[str, Any]
                if isinstance(arguments_payload, dict):
                    arguments = arguments_payload
                elif isinstance(arguments_payload, str):
                    try:
                        loaded = json.loads(arguments_payload)
                    except json.JSONDecodeError:
                        diagnostics.append(
                            _tool_error_like_diagnostic(
                                error_type="validation",
                                message="OpenAI function arguments are not valid JSON.",
                                original_payload=_to_raw_dict(tool_call),
                                is_retryable=True,
                            )
                        )
                        continue
                    if not isinstance(loaded, dict):
                        diagnostics.append(
                            _tool_error_like_diagnostic(
                                error_type="validation",
                                message="OpenAI function arguments JSON must be an object.",
                                original_payload=_to_raw_dict(tool_call),
                            )
                        )
                        continue
                    arguments = loaded
                else:
                    diagnostics.append(
                        _tool_error_like_diagnostic(
                            error_type="validation",
                            message="OpenAI function arguments must be JSON object text.",
                            original_payload=_to_raw_dict(tool_call),
                        )
                    )
                    continue

                call_id = _value(tool_call, "id")
                if not isinstance(call_id, str) or not call_id.strip():
                    call_id = f"call_{idx}"

                normalized_calls.append(
                    ToolCall(
                        id=call_id,
                        name=name,
                        arguments=arguments,
                        raw=_to_raw_dict(tool_call),
                    )
                )

        usage = _token_usage_from_raw(_value(raw, "usage"))
        raw_payload: dict[str, Any] | None = raw if isinstance(raw, dict) else {"raw_response": raw}
        if diagnostics:
            raw_payload = dict(raw_payload or {})
            raw_payload["diagnostics"] = diagnostics

        return LLMResponse(
            text=text,
            tool_calls=normalized_calls,
            is_final=not normalized_calls,
            usage=usage,
            raw=raw_payload,
        )


class AnthropicAdapter:
    @staticmethod
    def normalize(raw: Any) -> LLMResponse:
        blocks: list[Any]
        if isinstance(raw, dict):
            content = raw.get("content", [])
            blocks = content if isinstance(content, list) else []
        elif isinstance(_value(raw, "content"), list):
            blocks = _value(raw, "content")
        elif isinstance(raw, list):
            blocks = raw
        else:
            blocks = []

        text_parts: list[str] = []
        diagnostics: list[dict[str, Any]] = []
        normalized_calls: list[ToolCall] = []

        for idx, block in enumerate(blocks, start=1):
            if block is None:
                continue
            block_type = _value(block, "type")
            if block_type == "text":
                text = _value(block, "text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
                continue
            if block_type != "tool_use":
                continue

            name = _value(block, "name")
            if not isinstance(name, str) or not name.strip():
                diagnostics.append(
                        _tool_error_like_diagnostic(
                            error_type="validation",
                            message="Anthropic tool_use block missing name.",
                            original_payload=_to_raw_dict(block),
                        )
                    )
                continue

            arguments_payload = _value(block, "input", {})
            if not isinstance(arguments_payload, dict):
                diagnostics.append(
                        _tool_error_like_diagnostic(
                            error_type="validation",
                            message="Anthropic tool_use input must be an object.",
                            original_payload=_to_raw_dict(block),
                        )
                    )
                continue

            call_id = _value(block, "id")
            if not isinstance(call_id, str) or not call_id.strip():
                call_id = f"toolu_{idx}"

            normalized_calls.append(
                ToolCall(
                    id=call_id,
                    name=name,
                    arguments=arguments_payload,
                    raw=_to_raw_dict(block),
                )
            )

        joined_text = "\n".join(text_parts).strip()
        usage = _token_usage_from_raw(_value(raw, "usage"))
        raw_payload: dict[str, Any] | None = raw if isinstance(raw, dict) else {"content": raw}
        if diagnostics:
            raw_payload = dict(raw_payload or {})
            raw_payload["diagnostics"] = diagnostics

        return LLMResponse(
            text=joined_text or None,
            tool_calls=normalized_calls,
            is_final=not normalized_calls,
            usage=usage,
            raw=raw_payload,
        )


class JSONFallbackAdapter:
    @staticmethod
    def build_fallback_prompt(tools: list[ToolDescription]) -> str:
        compact_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.schema_dict,
            }
            for tool in tools
        ]
        return (
            "You are using JSON fallback tool calling.\n"
            "Return exactly one JSON object inside one fenced ```json block.\n"
            "Schema: "
            '{"text":"optional explanation","tool_calls":[{"id":"fallback_call_1","name":"tool_name","arguments":{}}],"is_final":false}\n'
            "Rules:\n"
            "- Use only tools listed below.\n"
            "- Keep arguments valid against each tool input_schema.\n"
            "- If no tool call is needed, return tool_calls as [] and is_final as true.\n"
            f"Available tools (compact): {json.dumps(compact_tools, separators=(',', ':'))}"
        )

    @staticmethod
    def _extract_last_valid_json_block(text: str) -> dict[str, Any] | None:
        if not isinstance(text, str):
            return None
        matches = _FENCED_JSON_BLOCK_RE.findall(text)
        last_valid: dict[str, Any] | None = None
        for block in matches:
            candidate = block.strip()
            if not candidate:
                continue
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                last_valid = loaded
        return last_valid

    @staticmethod
    def normalize(text: str, tools: list[ToolDescription], raw: dict | None = None) -> LLMResponse:
        payload = JSONFallbackAdapter._extract_last_valid_json_block(text)
        if payload is None:
            diagnostic = _tool_error_like_diagnostic(
                error_type="validation",
                message="No valid fenced JSON object was found in fallback output.",
                is_retryable=True,
            )
            return LLMResponse(
                text=text.strip() or None,
                tool_calls=[],
                is_final=True,
                raw=_with_diagnostic(raw, diagnostic),
            )

        response_text = payload.get("text")
        if not isinstance(response_text, str):
            response_text = None

        calls_payload = payload.get("tool_calls", [])
        if not isinstance(calls_payload, list):
            diagnostic = _tool_error_like_diagnostic(
                error_type="validation",
                message="fallback tool_calls must be a list.",
                original_payload=payload,
            )
            return LLMResponse(
                text=response_text,
                tool_calls=[],
                is_final=True,
                raw=_with_diagnostic(raw or payload, diagnostic),
            )

        schemas_by_name = {tool.name: tool.schema_dict for tool in tools}
        normalized_calls: list[ToolCall] = []
        for idx, call_payload in enumerate(calls_payload, start=1):
            if not isinstance(call_payload, dict):
                diagnostic = _tool_error_like_diagnostic(
                    error_type="validation",
                    message="Each fallback tool call must be an object.",
                    original_payload=payload,
                )
                return LLMResponse(
                    text=response_text,
                    tool_calls=[],
                    is_final=True,
                    raw=_with_diagnostic(raw or payload, diagnostic),
                )

            name = call_payload.get("name")
            if not isinstance(name, str) or name not in schemas_by_name:
                diagnostic = _tool_error_like_diagnostic(
                    error_type="not_found",
                    message=f"Unknown tool '{name}'.",
                    original_payload=payload,
                )
                return LLMResponse(
                    text=response_text,
                    tool_calls=[],
                    is_final=True,
                    raw=_with_diagnostic(raw or payload, diagnostic),
                )

            arguments = call_payload.get("arguments", {})
            if not isinstance(arguments, dict):
                diagnostic = _tool_error_like_diagnostic(
                    error_type="validation",
                    message=f"Tool '{name}' arguments must be an object.",
                    original_payload=payload,
                )
                return LLMResponse(
                    text=response_text,
                    tool_calls=[],
                    is_final=True,
                    raw=_with_diagnostic(raw or payload, diagnostic),
                )

            try:
                jsonschema.validate(instance=arguments, schema=schemas_by_name[name])
            except jsonschema.exceptions.ValidationError as exc:
                diagnostic = _tool_error_like_diagnostic(
                    error_type="validation",
                    message=f"Tool '{name}' arguments failed schema validation: {exc.message}",
                    original_payload=payload,
                )
                return LLMResponse(
                    text=response_text,
                    tool_calls=[],
                    is_final=True,
                    raw=_with_diagnostic(raw or payload, diagnostic),
                )

            call_id = call_payload.get("id")
            if not isinstance(call_id, str) or not call_id.strip():
                call_id = f"fallback_call_{idx}"

            normalized_calls.append(
                ToolCall(
                    id=call_id,
                    name=name,
                    arguments=arguments,
                    raw=call_payload,
                )
            )

        is_final = payload.get("is_final")
        if not isinstance(is_final, bool):
            is_final = not normalized_calls

        merged_raw = dict(raw) if isinstance(raw, dict) else {}
        merged_raw["fallback_payload"] = payload

        return LLMResponse(
            text=response_text,
            tool_calls=normalized_calls,
            is_final=is_final,
            raw=merged_raw or payload,
        )
