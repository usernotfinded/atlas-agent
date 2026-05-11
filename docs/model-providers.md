# Model Providers

Atlas Agent uses a provider catalog to normalize model selection across different AI APIs. You choose the provider and model; Atlas routes the configuration to the right places.

## Where configuration is stored

- **Non-secrets** (provider ID, model ID, base URL) go in `.atlas/config.toml`.
- **Secrets** (API keys) go in `.env.atlas`.
- `.env.atlas` is gitignored by default.

### Why Atlas never stores keys in `config.toml`
Atlas enforces strict separation between application state and credentials. `config.toml` is designed to be safe to share with your team or commit to version control if you choose to sync your workspace. By keeping secrets strictly isolated in `.env.atlas`, Atlas eliminates the risk of accidental API key leakage when pushing configurations or running audit logs.

## Supported providers

| Provider ID | Canonical env var | Auth style | Default Base URL | Key Required? | Notes |
|---|---|---|---|---|---|
| `openrouter` | `OPENROUTER_API_KEY` | Bearer | `https://openrouter.ai/api/v1` | Yes | Accepts optional metadata headers |
| `openai` | `OPENAI_API_KEY` | Bearer | `https://api.openai.com/v1` | Yes | |
| `anthropic` | `ANTHROPIC_API_KEY` | x-api-key | `https://api.anthropic.com` | Yes | Native Anthropic messages mode |
| `deepseek` | `DEEPSEEK_API_KEY` | Bearer | `https://api.deepseek.com` | Yes | |
| `kimi` | `MOONSHOT_API_KEY` | Bearer | `https://api.moonshot.cn/v1` | Yes | `KIMI_API_KEY` accepted as alias |
| `nvidia` | `NVIDIA_API_KEY` | Bearer | `https://integrate.api.nvidia.com/v1` | Yes | For cloud/API Catalog endpoints |
| `nvidia-local` | `NVIDIA_LOCAL_API_KEY` | None (by default) | *(user-provided)* | No | For local NIM / on-prem endpoints |
| `xai` | `XAI_API_KEY` | Bearer | `https://api.x.ai/v1` | Yes | |
| `google-gemini` | `GEMINI_API_KEY` | x-goog-api-key | `https://generativelanguage.googleapis.com/v1beta` | Yes | Native mode; `GOOGLE_API_KEY` has precedence |
| `gemini-openai-compatible` | `GEMINI_API_KEY` | Bearer | `.../v1beta/openai/` | Yes | OpenAI-compatible mode |
| `huggingface` | `HF_TOKEN` | Bearer | `https://api-inference.huggingface.co/v1` | Yes | `HUGGINGFACEHUB_API_TOKEN` legacy alias |
| `lmstudio` | *(None)* | None | `http://localhost:1234/v1` | No | Zero-auth local AI endpoint |
| `openai-compatible` | `ATLAS_OPENAI_COMPATIBLE_API_KEY` | Bearer (if key present) | *(user-provided)* | No | Strict isolation; never falls back to OpenAI |
| `custom` | `ATLAS_CUSTOM_API_KEY` | Bearer (if key present) | *(user-provided)* | No | Strict isolation |

Provider aliases (e.g. `or` for `openrouter`) are resolved automatically.

## Explicit Configurations

### Anthropic native auth
The `anthropic` provider uses Anthropic's native `anthropic_messages` API mode. Instead of a standard Bearer token, it automatically configures the correct HTTP headers required by Anthropic:
- `x-api-key`: Uses your `ANTHROPIC_API_KEY`.
- `anthropic-version`: Automatically set to the current default (e.g., `2023-06-01`).
- `content-type`: `application/json`.

### Gemini native vs Gemini OpenAI-compatible
Atlas supports two different operational modes for Google Gemini:
- **`google-gemini` (Native)**: This is the default. It uses the `x-goog-api-key` header and formats payloads according to the native Gemini API. If both `GOOGLE_API_KEY` and `GEMINI_API_KEY` exist, Google's documentation dictates that `GOOGLE_API_KEY` takes precedence. Atlas will warn you if this conflict is detected.
- **`gemini-openai-compatible`**: This uses the `Authorization: Bearer <key>` format and points to Google's specialized `v1beta/openai/` compatibility endpoint. It processes standard OpenAI chat completion payloads.

### NVIDIA cloud vs local/on-prem
NVIDIA NIM deployments differ between cloud and local:
- **`nvidia` (Cloud)**: Connects to NVIDIA's API catalog. Requires an `NVIDIA_API_KEY`. (Note: `NGC_API_KEY` is not used for standard inference).
- **`nvidia-local` (On-prem)**: Connects to a self-hosted NIM instance. You must provide a base URL. By default, it requires no authentication key, but respects `NVIDIA_LOCAL_API_KEY` if you have configured an auth proxy.

### LM Studio local setup
LM Studio is supported as a first-class local provider through OpenAI-compatible HTTP endpoints.
To set up LM Studio:
1. Start the LM Studio local server.
2. Set provider to `lmstudio`.
3. Set `base_url` (default is `http://localhost:1234/v1`).
4. Set the model ID matching the loaded LM Studio model.
5. No API key is required by default, and Atlas will not emit an Authorization header.

### OpenAI-compatible/custom endpoint isolation
Use the `openai-compatible` or `custom` providers for self-hosted, enterprise proxies, LiteLLM, or third-party OpenAI-compatible endpoints:

```bash
atlas model set openai-compatible my-model
```

Set the base URL via env var `ATLAS_OPENAI_COMPATIBLE_BASE_URL` or in `.atlas/config.toml`:

```toml
[model]
provider = "openai-compatible"
model = "my-model"

[providers.openai_compatible]
base_url = "https://my-api.example.com/v1"
```

**Strict Isolation:** These providers use dedicated keys (`ATLAS_OPENAI_COMPATIBLE_API_KEY` or `ATLAS_CUSTOM_API_KEY`) and **never** fall back to `OPENAI_API_KEY` or any other hosted provider's key. This protects your primary OpenAI credits from being accidentally leaked to a third-party server.

## Legacy and Internal Providers

### `local_command` (Legacy)
The `local_command` provider is a legacy/advanced option primarily kept for backward compatibility. It executes a local shell command rather than HTTP requests and is hidden from normal setup wizard flows.

### `NullProvider` (Internal)
`NullProvider` is an internal, test-only provider. It returns a deterministic response ("hold") and is hidden from standard model provider lists. It should not be used for agentic workflows.

## CLI commands

### List providers
```bash
atlas model providers
```
Shows user-facing providers, auth style, and default models. Run with `--include-legacy` or `--include-internal` to see hidden options.

### Show current selection
```bash
atlas model current
```
Shows the effective provider, model, API mode, base URL, and API key status (env var name and source, **never the key itself**).

### Interactive configuration
```bash
atlas model configure
```
Walks through selecting a provider, entering an API key (visible while typing, redacted on save), and picking a model.