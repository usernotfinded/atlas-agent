# Providers

Atlas Agent v0.5.1 is model-agnostic
 and provider-neutral.

## AI Provider Adapters
Adapters implement the `AIProvider` interface (`src/atlas_agent/providers/base.py`). They are responsible for communicating with AI backends and normalizing their output into internal `ToolCall` and `LLMResponse` objects.

Supported backends include:
- OpenAI, Anthropic, DeepSeek, Kimi/Moonshot, MiniMax.
- Aggregators: OpenRouter, NVIDIA NIM, Hugging Face.
- Any OpenAI-compatible custom endpoint.

## ToolRegistry
The `ToolRegistry` is the central validation layer. When a provider returns tool calls:
1.  **Normalization**: The adapter converts vendor-specific formats into internal `ToolCall` objects.
2.  **Schema Validation**: The `ToolRegistry` validates arguments against the tool's JSON Schema.
3.  **Safety Checks**: Every tool call is checked for `risk_gated`, `approval_gated`, and `audit_logged` flags.

## Trust Model
Provider output is strictly **advisory and untrusted**. No AI provider or model has a direct path to broker execution. Every action must be requested via a tool and verified by deterministic system guardrails.

