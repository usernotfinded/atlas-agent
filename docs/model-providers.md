# Model Providers

Atlas Agent uses a provider catalog to normalize model selection across different AI APIs. You choose the provider and model; Atlas routes the configuration to the right places.

## Where configuration is stored

- **Non-secrets** (provider ID, model ID, base URL) go in `.atlas/config.toml`.
- **Secrets** (API keys) go in `.env.atlas`.
- `.env.atlas` is gitignored by default.

Keys should be scoped, rotated regularly, and **never committed** to version control.

## Supported providers

| Provider ID | Label | Auth type | API mode | Auth header |
|---|---|---|---|---|
| `openrouter` | OpenRouter | API key | chat_completions | Bearer |
| `openai` | OpenAI | API key | chat_completions | Bearer |
| `anthropic` | Anthropic | API key | anthropic_messages | x-api-key |
| `deepseek` | DeepSeek | API key | chat_completions | Bearer |
| `kimi` | Kimi / Moonshot | API key | chat_completions | Bearer |
| `nvidia` | NVIDIA NIM | API key | chat_completions | Bearer |
| `xai` | xAI | API key | chat_completions | Bearer |
| `google-gemini` | Google Gemini | API key | chat_completions | Bearer |
| `huggingface` | Hugging Face | API key | chat_completions | Bearer |
| `local` | Local / Self-hosted | none | chat_completions | none |
| `custom` | Custom / OpenAI-compatible | API key | chat_completions | Bearer |

Provider aliases (e.g. `or` for `openrouter`) are resolved automatically.

## API key environment variables

Each provider looks for its key in **provider-specific** env vars only. Process environment variables override `.env.atlas`. One provider's key is **never used** for another provider.

| Provider | Canonical env var | Accepted aliases / notes |
|---|---|---|
| openrouter | `OPENROUTER_API_KEY` | — |
| openai | `OPENAI_API_KEY` | — |
| anthropic | `ANTHROPIC_API_KEY` | — |
| deepseek | `DEEPSEEK_API_KEY` | Do not use `ANTHROPIC_API_KEY` for DeepSeek |
| kimi | `MOONSHOT_API_KEY` | `KIMI_API_KEY` is accepted as alias |
| nvidia | `NVIDIA_API_KEY` | `NGC_API_KEY` is **not** equivalent; used for NGC/container workflows only |
| xai | `XAI_API_KEY` | — |
| google-gemini | `GOOGLE_API_KEY` | `GEMINI_API_KEY` accepted; `GOOGLE_API_KEY` takes precedence when both exist (matching Google SDK behavior) |
| huggingface | `HF_TOKEN` | `HUGGINGFACEHUB_API_TOKEN` legacy alias |
| local | none | No key required |
| custom | `ATLAS_CUSTOM_API_KEY` | Never falls back to `OPENAI_API_KEY` or `OPENROUTER_API_KEY` automatically |

### OpenRouter optional metadata

OpenRouter accepts two non-secret metadata headers:

- `OPENROUTER_SITE_URL` -> `HTTP-Referer`
- `OPENROUTER_SITE_NAME` -> `X-OpenRouter-Title`

These are optional and are read from environment variables, not `.env.atlas` secrets.

### `.env.atlas` example

```bash
# Required for your chosen provider only
OPENROUTER_API_KEY=sk-or-...

# Optional OpenRouter metadata (not secrets, but convenient in env)
OPENROUTER_SITE_URL=https://example.com
OPENROUTER_SITE_NAME=My Atlas Workspace
```

## CLI commands

### List providers

```bash
atlas model providers
```

Shows each provider, whether its API key is configured, and the default model.

### List models

```bash
atlas model list
atlas model list --provider openrouter
```

Shows the curated model catalog for one or all providers. Models marked with `*` are recommended defaults.

### Show current selection

```bash
atlas model current
```

Shows the effective provider, model, API mode, base URL, and API key status (env var name and source, **never the key itself**).

### Set provider and model

```bash
atlas model set openrouter openai/gpt-5.5
atlas model set openrouter:openai/gpt-5.5
atlas model set anthropic claude-sonnet-4.6
```

The first argument is the provider; the second is the model. If the model is not in the curated catalog, Atlas warns but still stores it.

### Interactive configuration

```bash
atlas model configure
```

Walks through selecting a provider, entering an API key if missing, and picking a model. Non-interactive environments should use `atlas model set` instead.

## Custom provider

Use the `custom` provider for self-hosted or third-party OpenAI-compatible endpoints:

```bash
atlas model set custom my-model
```

Set the base URL via env var `CUSTOM_BASE_URL` or in `.atlas/config.toml`:

```toml
[model]
provider = "custom"
model = "my-model"
base_url = "https://my-api.example.com/v1"
```

The custom provider uses `ATLAS_CUSTOM_API_KEY` and does **not** fall back to `OPENAI_API_KEY` or any other provider's key.

## Model catalog disclaimer

The model lists shipped with Atlas are **curated defaults** and **common options**. Model availability, pricing, and exact IDs depend on the provider and your account. If a model ID is not in the catalog, you can still set it with `atlas model set`; Atlas will warn but accept it.
