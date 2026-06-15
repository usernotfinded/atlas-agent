# Atlas Agent Product Demo Evidence Bundle

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What is the evidence bundle?

The product demo evidence bundle is a **local, read-only, deterministic artifact** produced by [`scripts/demo_product_walkthrough.sh`](../scripts/demo_product_walkthrough.sh) when run with `--output-dir <path>`. It gives reviewers, marketplace operators, and founders a concrete set of files they can inspect to confirm that the demo ran in paper/dry-run mode, used no credentials, made no provider or broker calls, and generated local backtest/audit artifacts.

The bundle does **not** prove profitability, production readiness, or that live trading is safe. It proves workflow mechanics and safety-boundary behavior only.

## Bundle contents

| File | Purpose |
|---|---|
| `evidence.json` | Machine-readable schema with safety booleans, command list, artifact paths, and output file references. |
| `summary.md` | Human-readable summary of what the bundle proves and does not prove. |
| `safety-boundaries.md` | Table of safety checks (live trading, provider execution, broker execution, credentials, network). |
| `artifacts-index.md` | Index of captured command outputs and copied workspace artifacts. |
| `commands.txt` | List of `atlas` commands executed during the demo. |
| `checksums.sha256` | SHA-256 checksums of every file in the bundle (except this file). |
| `outputs/*.txt` | Captured stdout/stderr from each `atlas` command run during the demo. |
| `artifacts/*` | Copies of safe workspace files such as `.atlas/config.toml`, `.atlas/discipline.md`, and the latest backtest result/report. |

## Generate a bundle

```bash
python3.11 -m pip install -e .
./scripts/demo_product_walkthrough.sh --output-dir ./artifacts/product_demo/my-evidence
```

Use `--deterministic` to produce stable timestamps and sorted output for tests or reproducible diffs:

```bash
./scripts/demo_product_walkthrough.sh --output-dir ./artifacts/product_demo/my-evidence --deterministic
```

The script will:

1. Create an isolated temporary workspace.
2. Apply the safe discipline profile and demo symbol.
3. Capture `atlas validate`, `atlas doctor --json`, paper dry-run, local backtest, and audit verification outputs.
4. Run [`scripts/build_product_demo_evidence.py`](../scripts/build_product_demo_evidence.py) to package the bundle.
5. Write the bundle to the directory you specified.

The default demo still runs without `--output-dir` and behaves exactly as before.

## Validate a bundle

```bash
python3.11 scripts/check_product_demo_evidence.py ./artifacts/product_demo/my-evidence
```

JSON output:

```bash
python3.11 scripts/check_product_demo_evidence.py ./artifacts/product_demo/my-evidence --json
```

The checker fails closed if any of the following are true:

- A required file is missing.
- `evidence.json` has an unsafe value such as `live_trading_enabled: true`.
- A captured command implies live mode, network access, broker submission, or provider execution.
- A secret-like pattern or forbidden marketing claim appears in any bundle file.
- A recorded checksum does not match the file.

## Evidence JSON schema

Key fields (all required):

| Field | Expected value | Meaning |
|---|---|---|
| `schema_version` | `"atlas-product-demo-evidence/1.0"` | Bundle schema version. |
| `generated_at` | ISO-8601 timestamp or deterministic placeholder | When the bundle was produced. |
| `atlas_version` | e.g. `"0.6.11"` | Atlas version that produced the bundle. |
| `demo_mode` | `"paper/dry-run"` | Mode the demo ran in. |
| `live_trading_enabled` | `false` | Live trading must not be enabled. |
| `provider_execution` | `false` | No real provider/LLM execution occurred. |
| `broker_execution` | `false` | No broker order submission occurred. |
| `credentials_loaded` | `false` | No API keys or broker credentials were loaded. |
| `network_required` | `false` | No network calls were required. |
| `demo_commands_run` | list of strings | Commands executed during the demo. |
| `output_files` | object | Relative paths to captured command outputs. |
| `artifact_paths` | object | Relative paths to copied workspace artifacts. |
| `safety_checks_summary` | object of booleans | All values must be `true`. |

## Safety guarantees and limits

**The bundle guarantees:**

- The demo ran in `paper/dry-run` mode.
- No credentials were loaded by the demo path.
- No provider or broker network calls were made.
- Local safety checks (`atlas validate`, `atlas doctor --json`) reported live trading disabled and provider/broker execution blocked.
- Local backtest and audit artifacts were generated or verified.

**The bundle does NOT guarantee:**

- That Atlas is safe for live trading in any other configuration.
- Strategy correctness, profitability, or future performance.
- Production readiness, compliance, or operational suitability.
- That a modified copy of Atlas has the same safety posture.

## How reviewers use it

1. Run the demo with `--output-dir` or request a pre-generated bundle.
2. Inspect `summary.md` and `safety-boundaries.md` for the safety narrative.
3. Open `evidence.json` to confirm all safety booleans are `false` or `true` as expected.
4. Check `outputs/validate.txt` and `outputs/doctor.txt` to see the original `atlas validate` / `atlas doctor --json` output.
5. Verify `checksums.sha256` with `sha256sum -c checksums.sha256` (Linux) or `shasum -a 256 -c checksums.sha256` (macOS).
6. Run `python3.11 scripts/check_product_demo_evidence.py <bundle-dir>` to repeat the deterministic checks.

## Marketplace evaluation

Marketplace operators can ask candidates to submit the bundle alongside the demo script. Because the bundle is local, read-only, and contains no credentials, it can be shared without exposing secrets. It provides a deterministic baseline that the candidate's checkout can reproduce the paper-only demo path and pass the bundled checker.

## Related docs and scripts

- [Product Demo and Marketplace Readiness Pack](product-demo-pack.md) — overview of the paper-only demo package.
- [Product Demo Walkthrough Script](../scripts/demo_product_walkthrough.sh) — the demo that produces the bundle.
- [Evidence Builder](../scripts/build_product_demo_evidence.py) — packages captured outputs into the bundle.
- [Evidence Checker](../scripts/check_product_demo_evidence.py) — deterministic validation of a bundle.
- [Marketplace Listing](marketplace-listing.md) — safe public description.
- [Autonomy Roadmap](autonomy-roadmap.md) — bounded autonomy levels.
