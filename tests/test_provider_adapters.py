from __future__ import annotations

import urllib.request

from atlas_agent.providers.adapters import (
    AnthropicAdapter,
    JSONFallbackAdapter,
    OpenAICompatibleAdapter,
)
from atlas_agent.providers.base import BaseAIProvider
from atlas_agent.providers.local_command import LocalCommandProvider
from atlas_agent.providers.openai_compatible import OpenAICompatibleProvider
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


def _quote_tool() -> ToolDescription:
    return ToolDescription(
        name="get_quote",
        description="Get latest quote",
        schema_dict={
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symbols"],
            "additionalProperties": False,
        },
    )


def test_openai_tool_call_normalization() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_quote",
                                "arguments": '{"symbols":["AAPL"]}',
                            },
                        }
                    ]
                }
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }

    response = OpenAICompatibleAdapter.normalize(raw)

    assert response.text is None
    assert response.is_final is False
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_123"
    assert response.tool_calls[0].name == "get_quote"
    assert response.tool_calls[0].arguments == {"symbols": ["AAPL"]}
    assert response.tool_calls[0].raw == raw["choices"][0]["message"]["tool_calls"][0]
    assert response.usage is not None
    assert response.usage.total_tokens == 20


def test_openai_final_text_response() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "content": "No action needed.",
                }
            }
        ]
    }

    response = OpenAICompatibleAdapter.normalize(raw)

    assert response.text == "No action needed."
    assert response.tool_calls == []
    assert response.is_final is True


def test_openai_invalid_arguments_json_is_safe() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_bad",
                            "type": "function",
                            "function": {
                                "name": "get_quote",
                                "arguments": '{"symbols": ["AAPL"]',
                            },
                        }
                    ]
                }
            }
        ]
    }

    response = OpenAICompatibleAdapter.normalize(raw)

    assert response.tool_calls == []
    assert response.is_final is True
    assert response.raw is not None
    assert "diagnostics" in response.raw


def test_anthropic_tool_use_normalization() -> None:
    raw = {
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "get_quote",
                "input": {"symbols": ["AAPL"]},
            }
        ]
    }

    response = AnthropicAdapter.normalize(raw)

    assert response.text is None
    assert response.is_final is False
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "toolu_123"
    assert response.tool_calls[0].name == "get_quote"
    assert response.tool_calls[0].arguments == {"symbols": ["AAPL"]}


def test_anthropic_mixed_text_and_tool_use_blocks() -> None:
    raw = {
        "content": [
            {"type": "text", "text": "Analyzing..."},
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "get_quote",
                "input": {"symbols": ["AAPL"]},
            },
            {"type": "text", "text": "Need fresh quote."},
        ]
    }

    response = AnthropicAdapter.normalize(raw)

    assert response.text == "Analyzing...\nNeed fresh quote."
    assert len(response.tool_calls) == 1
    assert response.is_final is False


def test_anthropic_raw_id_preserved() -> None:
    raw = [
        {
            "type": "tool_use",
            "id": "toolu_abc",
            "name": "get_quote",
            "input": {"symbols": ["AAPL"]},
        }
    ]

    response = AnthropicAdapter.normalize(raw)

    assert response.tool_calls[0].id == "toolu_abc"
    assert response.tool_calls[0].raw is not None
    assert response.tool_calls[0].raw.get("id") == "toolu_abc"


def test_json_fallback_valid_tool_call() -> None:
    text = """```json
{"text":"Checking quote","tool_calls":[{"id":"fallback_call_1","name":"get_quote","arguments":{"symbols":["AAPL"]}}],"is_final":false}
```"""

    response = JSONFallbackAdapter.normalize(text, [_quote_tool()])

    assert response.text == "Checking quote"
    assert response.is_final is False
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "fallback_call_1"
    assert response.tool_calls[0].name == "get_quote"


def test_json_fallback_malformed_json() -> None:
    text = """```json
{"text":"oops","tool_calls":[}
```"""

    response = JSONFallbackAdapter.normalize(text, [_quote_tool()])

    assert response.tool_calls == []
    assert response.is_final is True
    assert response.raw is not None
    assert response.raw["diagnostic"]["error_type"] == "validation"


def test_json_fallback_unknown_tool_rejected() -> None:
    text = """```json
{"text":"try","tool_calls":[{"id":"fallback_call_1","name":"unknown_tool","arguments":{"symbols":["AAPL"]}}],"is_final":false}
```"""

    response = JSONFallbackAdapter.normalize(text, [_quote_tool()])

    assert response.tool_calls == []
    assert response.is_final is True
    assert response.raw is not None
    assert response.raw["diagnostic"]["error_type"] == "not_found"


def test_json_fallback_invalid_args_rejected() -> None:
    text = """```json
{"text":"try","tool_calls":[{"id":"fallback_call_1","name":"get_quote","arguments":{"ticker":"AAPL"}}],"is_final":false}
```"""

    response = JSONFallbackAdapter.normalize(text, [_quote_tool()])

    assert response.tool_calls == []
    assert response.is_final is True
    assert response.raw is not None
    assert response.raw["diagnostic"]["error_type"] == "validation"


def test_json_fallback_chooses_last_valid_json_block() -> None:
    text = """
```json
{"text":"first","tool_calls":[{"id":"fallback_call_1","name":"get_quote","arguments":{"symbols":["MSFT"]}}],"is_final":false}
```
noise
```json
{"text":"second","tool_calls":[{"id":"fallback_call_2","name":"get_quote","arguments":{"symbols":["AAPL"]}}],"is_final":false}
```
"""

    response = JSONFallbackAdapter.normalize(text, [_quote_tool()])

    assert response.text == "second"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "fallback_call_2"
    assert response.tool_calls[0].arguments == {"symbols": ["AAPL"]}


class _SummaryTestProvider(BaseAIProvider):
    def __init__(self) -> None:
        self.last_call: dict | None = None

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.last_call = {
            "system_prompt": system_prompt,
            "messages": messages,
            "tools": tools,
            "model": model,
            "temperature": temperature,
        }
        return LLMResponse(text=" short summary ", tool_calls=[], is_final=True)

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=10_000,
            supports_native_tools=False,
            supports_json_mode=False,
            supports_streaming=False,
            provider_name="summary_test",
            model_name="summary-model",
        )


def test_summarize_uses_complete_without_tools() -> None:
    provider = _SummaryTestProvider()

    summary = provider.summarize(text="Very long text", max_tokens=64)

    assert summary == "short summary"
    assert provider.last_call is not None
    assert provider.last_call["tools"] == []
    assert provider.last_call["temperature"] == 0.0
    assert "summarization assistant" in provider.last_call["system_prompt"].lower()
    assert "64 tokens" in provider.last_call["messages"][0]["content"]


def test_capabilities_return_expected_values() -> None:
    openai_caps = OpenAICompatibleProvider(default_model="gpt-test").capabilities()
    assert openai_caps.supports_native_tools is True
    assert openai_caps.supports_json_mode is True
    assert openai_caps.provider_name == "openai_compatible"
    assert openai_caps.model_name == "gpt-test"

    local_caps = LocalCommandProvider(command="echo hi").capabilities()
    assert local_caps.supports_native_tools is False
    assert local_caps.supports_streaming is False
    assert local_caps.provider_name == "local_command"


def test_adapter_normalization_makes_no_network_calls(
    monkeypatch,
) -> None:
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    response = OpenAICompatibleAdapter.normalize(
        {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                    }
                }
            ]
        }
    )

    assert response.text == "ok"
