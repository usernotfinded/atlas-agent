# Provider Preflight Dry-Run Demo

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This demo runs the local provider preflight pipeline:

```text
generate -> validate -> bundle -> verify bundle -> smoke report
```

It is dry-run only and local-only. It does not call providers, use the
network, load credentials, import provider SDKs, touch brokers, enable live
trading, create pending orders, or approve orders.

## One-command smoke demo

Use this command for the safest reviewer demo:

```bash
atlas providers smoke-preflight-chain \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary" \
  --max-context-chars 4000 \
  --output-dir artifacts/provider_preflight_smoke/demo
```

This writes local artifacts under `artifacts/provider_preflight_smoke/demo`.
It does not call a provider and does not require provider credentials.

## Step-by-step pipeline

Use these commands when you want to inspect each stage separately:

```bash
atlas providers preflight \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary" \
  --max-context-chars 4000 \
  --output artifacts/provider_preflight/demo-call-plan.json

atlas providers validate-preflight \
  artifacts/provider_preflight/demo-call-plan.json

atlas providers bundle-preflight \
  artifacts/provider_preflight/demo-call-plan.json \
  --output-dir artifacts/provider_preflight_bundles/demo

atlas providers verify-preflight-bundle \
  artifacts/provider_preflight_bundles/demo
```

## Expected artifacts

| File | Created by | Purpose |
|---|---|---|
| `call-plan.json` | `bundle-preflight`, `smoke-preflight-chain` | Dry-run provider call-plan copy. |
| `validation-report.json` | `bundle-preflight`, `smoke-preflight-chain` | Local validation evidence for the call-plan. |
| `manifest.json` | `bundle-preflight`, `smoke-preflight-chain` | Bundle manifest with expected files and hashes. |
| `sha256sums.txt` | `bundle-preflight`, `smoke-preflight-chain` | Relative-path SHA-256 evidence for bundle files. |
| `smoke-report.json` | `smoke-preflight-chain` | End-to-end smoke-chain result and closed safety summary. |

The manual pipeline writes bundle files under
`artifacts/provider_preflight_bundles/demo`. The smoke command writes the same
bundle evidence plus `smoke-report.json` under
`artifacts/provider_preflight_smoke/demo`.

## Safety guarantees

| Capability | Status |
|---|---|
| Provider call | Disabled |
| Network use | Disabled |
| Credentials loaded | Disabled |
| Provider SDK imports | Disabled |
| Broker touched | Disabled |
| Live trading | Disabled |
| Pending orders | Disabled |
| Order approval | Disabled |

Provider preflight artifacts are audit evidence only. They do not authorize
provider execution, broker execution, live trading, pending orders, or order
approval.

## Troubleshooting

- If validation fails, inspect the error and regenerate the call-plan.
- If bundle verification fails, treat the bundle as tampered or incomplete.
- If the smoke chain fails, do not use the artifacts as evidence.
- Do not bypass validation by editing JSON manually.
