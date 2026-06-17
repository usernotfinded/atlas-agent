# CAND-024 Plan — Paper Mode Offline Provider Isolation and No-Network Gate

## Goal
Make Atlas paper-mode agentic workflows runnable with no provider API key and no network access, while preserving live-mode fail-closed behavior and all safety invariants.

## Constraints (from AGENTS.md and CAND-024 prompt)
- No live trading / live submit / broker execution enabled.
- No real provider calls in tests/checkers/demos.
- No protected runtime boundary changes unless justified.
- Source/package version stays `0.6.12`; v0.6.13 stays planning-only.
- No tags, releases, PyPI publish.
- No credentials/secrets, no profit claims, no claims that risk is absent, and no live-readiness claims.

## Root cause
`src/atlas_agent/agent/runner.py` resolves an AI provider unconditionally before running the agent loop, even in paper mode. The default config provider is `openai`; with no key the provider call fails with a transport/operation error, which is reported as a paper-trading failure.

## Implementation tasks

1. **Wire the existing `NullProvider` into the provider factory**
   - File: `src/atlas_agent/providers/factory.py`
   - Add a branch so `build_provider_from_runtime` returns `NullProvider()` when `provider_id == "null"`.
   - Keep all other provider behavior unchanged.

2. **Add paper-mode provider fallback in the agent runner**
   - File: `src/atlas_agent/agent/runner.py`
   - Compute `effective_mode` before provider resolution.
   - When `effective_mode == "paper"` and the resolved provider would require missing credentials (or is explicitly `null`), use `NullProvider` instead of calling the network provider.
   - Log/audit the fallback clearly.
   - Live mode must continue to fail closed when provider/broker config is missing.

3. **Add an explicit `--offline` flag to the paper run commands**
   - Files: `src/atlas_agent/cli.py` (`run` parser and `agent run` parser)
   - When `--offline` is passed, set `config.model.provider = "null"` before invoking the runner so the run is deterministic and provider-free.
   - Update `tests/fixtures/cli_command_contract.json` if the contract checker requires it.

4. **Add deterministic no-network checker**
   - File: `scripts/check_paper_provider_isolation.py`
   - Validate doc presence, cross-links, release metadata, demo script offline path, forbidden claims, no credentials, no v0.6.13 release claim.
   - Support `--json`; exit codes 0/1/2.

5. **Add focused tests**
   - File: `tests/test_paper_provider_isolation.py`
   - Cover: checker passes, JSON mode, missing-doc failures, unsafe-claim failures, release/PyPI failures, demo-script credential failure, paper run works in scrubbed env, no real provider network call, live mode still fails safely, explicit `--offline` path, no file mutation.

6. **Update docs and candidate planning files**
   - New: `docs/paper-provider-isolation.md`
   - Update: `README.md`, `docs/autonomous-paper-workflow.md`, `docs/bounded-live-autonomy-governance.md`, `docs/autonomy-roadmap.md`, `docs/public-launch-readiness.md`, `docs/reviewer-checklist.md`, `docs/trust/README.md`, `docs/releases/v0.6.13-candidate-selection.md`, `docs/releases/v0.6.13-candidates.md`, `docs/releases/v0.6.13-candidates.json`, `docs/releases/v0.6.13-plan.md`.
   - Add CAND-024 as implemented/current after completion.

7. **Update demo script**
   - File: `scripts/demo_autonomous_paper_workflow.sh`
   - Replace/augment the dry-run-only `run --mode paper` step with the provider-free offline path (`--offline`) so the demo exercises a real paper cycle without credentials.
   - Keep all evidence outputs untracked.

8. **Integrate gates**
   - Files: `scripts/dev_check.sh`, `scripts/ci_check.sh`, `scripts/release_check.sh`, `.github/workflows/ci.yml`
   - Run the new checker and its tests in the quick/local gates.

9. **Validation, commit, push, CI verification**
   - Run all required checks and tests.
   - Stage explicit files only; commit and push to `main`.
   - Verify GitHub Actions passes.

## Safety invariants to verify
- `atlas run --mode paper --symbol ATLAS-DEMO --max-cycles 1` completes offline in a scrubbed environment.
- `atlas run --mode live` still fails safely with missing broker/provider config.
- Provider-free paper path does not bypass risk, approval, kill-switch, or audit gates.
- No protected runtime boundary changes in `config`, `brokers`, `execution`, `safety`, `risk`.
