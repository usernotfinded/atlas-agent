# Public Launch Readiness

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Public launch status

Atlas Agent is a **v0.6.12 public release for sandbox/paper/preflight workflows**. It is ready to be shown publicly for review, evaluation, and contribution, but it is **not a live-trading-ready product**. The current tagged public GitHub release is `v0.6.12`; `v0.6.11`, `v0.6.10`, `v0.6.9`, `v0.6.8`, `v0.6.7`, `v0.6.6`, `v0.6.5`, `v0.6.4`, `v0.6.3`, `v0.6.2`, `v0.6.1`, and `v0.6.0` are historical.

The source package version on `main` is `0.6.12`. `v0.6.12` is tagged and released.

This document explains what is verified, what remains disabled, and what reviewers should check.

## Verified locally

The following checks pass on a clean local clone without credentials or network calls:

- `python3.11 scripts/check_version_consistency.py` — version consistency across package, code, and docs
- `python3.11 scripts/check_forbidden_claims.py` — no prohibited safety or profit claims
- `python3.11 scripts/check_public_docs_consistency.py` — public docs are safe and consistent
- `python3.11 scripts/verify_readme_quickstart.py` — README quickstart is safe and verifiable
- `python3.11 scripts/check_rc1_cutover.py` — RC cutover checks pass
- `python3.11 scripts/check_clean_install.py` — clean install works without credentials or network
- `python3.11 scripts/check_package_distribution.py` — package builds and metadata is correct
- `python3.11 scripts/check_public_launch_readiness.py` — launch materials are present and safe
- `python3.11 scripts/check_public_launch_messaging.py` — launch messaging is safe
- `python3.11 scripts/check_product_demo_pack.py` — product demo and marketplace readiness pack is present and safe
- `python3.11 scripts/check_product_demo_evidence.py <bundle-dir>` — generated evidence bundle is schema-valid and safe
- `python3.11 scripts/check_reviewer_trust_snapshot.py --self-test` — reviewer trust snapshot builds and validates locally
- `python3.11 -m pytest tests/test_reviewer_trust_snapshot.py -q` — trust snapshot tests pass
- `python3.11 scripts/check_reviewer_trust_snapshot_workflow.py` — reviewer trust snapshot workflow is safe
- `python3.11 -m pytest tests/test_reviewer_trust_snapshot_workflow.py -q` — trust snapshot workflow tests pass
- `python3.11 scripts/check_release_assurance_snapshot_integration.py` — release assurance snapshot integration is safe
- `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -q` — release assurance snapshot integration tests pass
- `python3.11 scripts/check_release_assurance_bundle_workflow.py` — release assurance bundle workflow path is safe
- `python3.11 -m pytest tests/test_release_assurance_bundle_workflow.py -q` — release assurance bundle workflow tests pass
- `python3.11 scripts/check_release_assurance_workflow_artifact.py <path>` — downloaded release-assurance-bundle-demo artifact is valid
- `python3.11 -m pytest tests/test_release_assurance_workflow_artifact.py -q` — release assurance workflow artifact tests pass
- `docs/security/release-assurance-diagnostics.md` — release-assurance failure diagnostics, redaction rules, and `--diagnostics-json` usage are documented
- `python3.11 scripts/check_release_assurance_diagnostics_workflow.py` — release assurance diagnostics workflow path is safe, including the opt-in `validate_diagnostics_artifact` input and validator-before-upload ordering
- `python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q` — release assurance diagnostics workflow tests pass
- `python3.11 scripts/check_release_assurance_diagnostics_artifact.py <path>` — downloaded release-assurance-diagnostics artifact is valid and redacted
- `python3.11 -m pytest tests/test_release_assurance_diagnostics_artifact.py -q` — release assurance diagnostics artifact tests pass
- `python3.11 scripts/check_release_assurance_diagnostics_artifact_workflow.py` — release assurance diagnostics artifact revalidation workflow is safe
- `python3.11 -m pytest tests/test_release_assurance_diagnostics_artifact_workflow.py -q` — release assurance diagnostics artifact revalidation workflow tests pass
- `python3.11 -m pytest tests/test_public_launch_readiness.py` — launch readiness tests pass
- `python3.11 -m pytest tests/test_public_launch_messaging.py` — launch messaging tests pass
- `python3.11 -m pytest tests/test_product_demo_pack.py` — product demo pack tests pass
- `python3.11 -m pytest tests/test_public_repo_hygiene.py` — repository hygiene tests pass
- `python3.11 scripts/check_v0612_release_cutover.py` — v0.6.12 public-release cutover state is valid
- `python3.11 scripts/check_v0612_release_prep.py --post-release` — v0.6.12 post-release state is valid
- `./scripts/release_check.sh --quick` — quick release gate passes

## Verified in CI

GitHub Actions runs the following on every push and pull request to `main`:

- Version consistency, forbidden claims scan, public docs consistency
- README quickstart verification, RC cutover check
- Clean install dry-run and verification
- Package distribution dry-run and verification
- Focused pytest subset (clean install, package distribution, RC cutover, changelog, public docs, README quickstart, release scripts, CI workflows, docs v0.4.0)
- pip check, git diff --check, protected staged files check
- Release check quick gate

No CI workflow publishes, uploads, tags, or pushes.

## What remains disabled

- **Live trading** is disabled by default and requires explicit multi-factor opt-in.
- **Provider execution** remains locked — no real LLM/provider calls are made by default.
- **Broker order submission** is blocked by `can_submit=false`.
- **Credentials** are not loaded unless explicitly configured.
- **Trust** remains blocked — mock responses in safety workflows are explicitly not trusted.

## Safe demo path

A new visitor can safely verify Atlas Agent locally:

```bash
python3.11 -m pip install -e .
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol DEMO-SYMBOL
atlas validate
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
```

No broker, no network, no credentials, no live trading.

## Repository hygiene status

- `SECURITY.md` present with safety posture
- `CONTRIBUTING.md` present with safety boundaries
- Issue templates present (bug report, docs issue, safety concern, feature request)
- PR template present with protected boundary reminders
- `docs/public-repo-hygiene.md` present
- `docs/public-launch-readiness.md` present (this file)
- `docs/github-repo-settings.md` present
- `docs/ci-release-gates.md` present
- `docs/package-distribution-verification.md` present
- `docs/clean-install-verification.md` present
- `docs/external-reviewer-walkthrough.md` present
- `docs/reviewer-checklist.md` present
- `docs/public-launch-messaging.md` present
- `docs/feedback-request-guide.md` present
- `docs/public-faq.md` present
- `docs/product-demo-pack.md` present
- `docs/marketplace-listing.md` present
- `docs/autonomy-roadmap.md` present
- `docs/product-demo-evidence.md` present
- `docs/releases/v0.6.12-candidate-readiness.md` present — v0.6.12 candidate readiness consolidation doc
- `docs/releases/v0.6.12.md` present — v0.6.12 release notes (current public)
- `docs/trust/v0.6.12-status.md` present — v0.6.12 trust status (current public)

## Release artifacts status

- Package distribution dry-run does not publish or upload.
- Clean install verification does not access PyPI by default.
- No `dist/`, `build/`, or `*.egg-info/` artifacts are staged.
- Artifact retention visibility is provided by the manual `release-assurance-artifact-retention-audit` workflow; it is read-only and does not download, delete, or clean up artifacts.
- Version on `main` is `0.6.12`; latest stable public GitHub release is `v0.6.12`. `v0.6.11`, `v0.6.10`, `v0.6.9`, `v0.6.8`, `v0.6.7`, `v0.6.6`, `v0.6.5`, `v0.6.4`, `v0.6.3`, `v0.6.2`, `v0.6.1`, and `v0.6.0` are historical.
- `v0.6.12` is the current public release (tagged and published on GitHub); `v0.6.13` is the next planning line.
- [v0.6.12 Post-Release Evidence](./releases/v0.6.12-post-release-evidence.md) records the deterministic cutover evidence.
- [v0.6.13 Planning Seed](./releases/v0.6.13-plan.md) seeds the next planning line and does not claim a release.

## Known limitations

- This is not a live-trading-ready product. Stable v0.5.8 refers to release/documentation/process stability, not trading correctness or real-money safety.
- Live trading is explicitly disabled by default.
- Provider execution is not implemented for real providers.
- Broker adapters are in beta (Alpaca read-only sync available; others deferred).
- Dashboard is basic and read-only.
- Self-improvement features are early-stage.
- Backtesting is a research tool; historical results do not guarantee future performance.

## Reviewer onboarding

For a structured review path, see:
- [External Reviewer Walkthrough](external-reviewer-walkthrough.md) — 10–15 minute safe review path
- [Reviewer Checklist](reviewer-checklist.md) — checklist before trusting or recommending
- [Public FAQ](public-faq.md) — answers to common questions
- [Feedback Request Guide](feedback-request-guide.md) — how to ask for feedback safely

## What reviewers should check

1. Verify the README "What this is" and "What this is not" sections match your expectations.
2. Run `./scripts/release_check.sh --quick` locally.
3. Run `python3.11 scripts/check_public_launch_readiness.py`.
4. Run `python3.11 scripts/check_reviewer_onboarding.py`.
5. Confirm no live-trading readiness claims exist in docs.
6. Confirm no profitability claims exist in docs.
7. Confirm protected boundaries show no diff:
   ```bash
   git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
   git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
   ```

## What not to assume

- Do not assume Atlas is safe to trade real money with.
- Do not assume historical backtest results predict future performance.
- Do not assume provider execution is enabled or trustworthy.
- Do not assume the presence of broker adapters implies live trading readiness.
- Do not assume this is financial advice.
