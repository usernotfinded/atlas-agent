# Reviewer Checklist

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Use this checklist before trusting or recommending the Atlas Agent repository.

## Repository hygiene

- [ ] README says what the project is and is not
- [ ] SECURITY.md exists
- [ ] CONTRIBUTING.md exists
- [ ] CHANGELOG.md exists with current version entry
- [ ] Issue and PR templates exist
- [ ] Release notes exist for current version
- [ ] Public launch messaging docs present and safe
- [ ] No package artifacts (`dist/`, `build/`, `*.egg-info/`) are staged

## README clarity

- [ ] Current status references the expected version
- [ ] "What this is" section is present
- [ ] "What this is not" section is present
- [ ] Links to SECURITY.md, CONTRIBUTING.md, and changelog/release notes
- [ ] No live-trading readiness claims
- [ ] No profitability or performance guarantees

## Safety wording

- [ ] "Not financial advice" appears in public docs
- [ ] "Live trading disabled by default" appears
- [ ] "Provider execution remains locked" appears
- [ ] "Trust remains blocked" appears
- [ ] No forbidden positive claims (e.g., claims that live trading is ready, profit guarantees, etc.)

## Installation path

- [ ] `python3.11 -m pip install -e .` works
- [ ] `atlas --help` works after install
- [ ] No secrets or credentials are required for default verification
- [ ] No credentials required for default verification

## CI and release gates

- [ ] CI quick gate runs version, claims, docs, install, and package checks
- [ ] CI does not publish, upload, tag, or push
- [ ] `scripts/release_check.sh --quick` passes locally
- [ ] No secrets required in CI workflows
- [ ] `.github/workflows/release-assurance-artifact-retention-audit.yml` is `workflow_dispatch` only, declares `contents: read` and `actions: read` permissions, references no arbitrary secrets, and performs only read-only artifact retention visibility checks (no download, delete, cleanup, tag, release, or PyPI); `scripts/check_release_assurance_artifact_retention_audit.py` and `python3.11 -m pytest tests/test_release_assurance_artifact_retention_audit.py -q` pass

## Package checks

- [ ] `scripts/check_package_distribution.py --dry-run` passes
- [ ] Package distribution dry-run does not publish or upload
- [ ] Clean install check passes or dry-run passes

## Provider safety workflow

- [ ] Provider safety dossier is described as sandbox-only and offline
- [ ] No broker/order path in provider safety workflows
- [ ] No credentials loaded by default in safety workflows
- [ ] Paper mode can run without provider credentials or network ([docs/paper-provider-isolation.md](paper-provider-isolation.md))
- [ ] Paper strategy robustness can run across deterministic synthetic regimes without provider credentials, broker credentials, network, or live mode ([docs/paper-strategy-robustness.md](paper-strategy-robustness.md))
- [ ] Paper portfolio stress constraints run on deterministic synthetic scenarios without provider credentials, broker credentials, network, or live mode ([docs/paper-portfolio-stress.md](paper-portfolio-stress.md))
- [ ] v0.6.14 paper portfolio evidence and final readiness audit are historical pre-cutover, paper-only, and local ([docs/releases/v0.6.14-paper-portfolio-evidence.md](releases/v0.6.14-paper-portfolio-evidence.md), [docs/releases/v0.6.14-final-readiness-audit.md](releases/v0.6.14-final-readiness-audit.md))
- [ ] Paper human review pack is deterministic, offline, non-executable, and derived from paper portfolio evidence; docs/demo/checker/tests are present ([docs/paper-human-review-pack.md](paper-human-review-pack.md), `scripts/demo_paper_human_review_pack.sh`, `scripts/check_paper_human_review_pack.py`, `tests/test_paper_human_review_pack.py`)
- [ ] Paper human review ledger is deterministic, offline, non-executable, and produces simulated review decisions from the CAND-001 review pack; docs/demo/checker/tests are present ([docs/paper-human-review-ledger.md](paper-human-review-ledger.md), `scripts/demo_paper_human_review_ledger.sh`, `scripts/check_paper_human_review_ledger.py`, `tests/test_paper_human_review_ledger.py`)
- [ ] Paper human review policy simulator is deterministic, offline, non-executable, evaluates the CAND-001 review pack and CAND-002 review ledger against explicit blocked-live policy rules, and produces a gate artifact; docs/demo/checker/tests are present ([docs/paper-human-review-policy.md](paper-human-review-policy.md), `scripts/demo_paper_human_review_policy.sh`, `scripts/check_paper_human_review_policy.py`, `tests/test_paper_human_review_policy.py`)
- [ ] Paper human review replay and regression gate is deterministic, offline, non-executable, replays the CAND-001 review pack, CAND-002 review ledger, and CAND-003 review policy, and verifies the paper chain remains intact with the live path blocked; docs/demo/checker/tests are present ([docs/paper-human-review-replay.md](paper-human-review-replay.md), `scripts/demo_paper_human_review_replay.sh`, `scripts/check_paper_human_review_replay.py`, `tests/test_paper_human_review_replay.py`)
- [ ] Paper human review evidence bundle and candidate closure gate is deterministic, offline, non-executable, closes the CAND-001 through CAND-004 paper human review chain, and produces a v0.6.15 closure evidence artifact; docs/checker/tests are present ([docs/releases/v0.6.15-paper-human-review-evidence.md](releases/v0.6.15-paper-human-review-evidence.md), `scripts/check_v0615_paper_human_review_evidence.py`, `tests/test_v0615_paper_human_review_evidence.py`)
- [ ] `docs/releases/v0.6.15-plan.md`, `docs/releases/v0.6.15-candidates.md`, and `docs/releases/v0.6.15-candidates.json` are planning-only and list CAND-001, CAND-002, CAND-003, CAND-004, and CAND-005 without claiming v0.6.15 is released

## Protected boundaries

- [ ] `git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk` shows no output
- [ ] `git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk` shows no output

## Product demo and marketplace readiness

- [ ] `README.md` Demos section links to `docs/product-demo-pack.md` and `scripts/demo_product_walkthrough.sh`.
- [ ] `docs/product-demo-pack.md`, `docs/marketplace-listing.md`, and `docs/autonomy-roadmap.md` are present.
- [ ] `scripts/demo_product_walkthrough.sh` is executable and uses `--mode paper --dry-run`.
- [ ] `scripts/check_product_demo_pack.py` is executable and passes.
- [ ] `scripts/build_product_demo_evidence.py` and `scripts/check_product_demo_evidence.py` are executable.
- [ ] Running `./scripts/demo_product_walkthrough.sh --output-dir <path>` produces a valid evidence bundle.
- [ ] `python3.11 scripts/check_product_demo_evidence.py <path>` passes on the generated bundle.
- [ ] `scripts/build_reviewer_trust_snapshot.py` and `scripts/check_reviewer_trust_snapshot.py` are executable.
- [ ] `python3.11 scripts/check_reviewer_trust_snapshot.py --self-test` passes.
- [ ] `python3.11 -m pytest tests/test_reviewer_trust_snapshot.py -q` passes.
- [ ] Running `python3.11 scripts/build_reviewer_trust_snapshot.py --output-dir <path>` produces a valid trust snapshot.
- [ ] `python3.11 scripts/check_reviewer_trust_snapshot.py <path>` passes on the generated snapshot.
- [ ] `.github/workflows/reviewer-trust-snapshot.yml` exists, is `workflow_dispatch` only, has `contents: read` permissions, references no secrets, and uploads a `reviewer-trust-snapshot` artifact.
- [ ] `python3.11 scripts/check_reviewer_trust_snapshot_workflow.py` passes.
- [ ] `python3.11 -m pytest tests/test_reviewer_trust_snapshot_workflow.py -q` passes.
- [ ] `python3.11 scripts/check_release_assurance_snapshot_integration.py` passes.
- [ ] `python3.11 -m pytest tests/test_release_assurance_snapshot_integration.py -q` passes.
- [ ] Running `python3.11 scripts/release_assurance.py --version v0.6.11 --output <dir> --include-reviewer-trust-snapshot` produces a valid assurance pack with a validated reviewer trust snapshot.
- [ ] `python3.11 -m pytest tests/test_release_assurance_bundle_manifest.py -q` passes.
- [ ] `python3.11 scripts/check_release_assurance_bundle_workflow.py` passes.
- [ ] `python3.11 -m pytest tests/test_release_assurance_bundle_workflow.py -q` passes.
- [ ] Running `bash scripts/demo_release_assurance_snapshot_bundle.sh --version v0.6.11 --output-dir <path> --deterministic` produces a valid baseline bundle, opt-in snapshot bundle, and manifest; `python3.11 scripts/check_release_assurance_bundle_manifest.py <path>` passes.
- [ ] `.github/workflows/release-assurance.yml` remains `workflow_dispatch` only, keeps `contents: read` permissions, references no secrets, and only runs the bundle demo when `run_bundle_demo` is explicitly set to `true`.
- [ ] `scripts/check_release_assurance_workflow_artifact.py` exists, is executable, and passes on a valid local artifact fixture.
- [ ] `python3.11 -m pytest tests/test_release_assurance_workflow_artifact.py -q` passes.
- [ ] Downloaded `release-assurance-bundle-demo` artifacts (extracted directory or `.zip`) pass `python3.11 scripts/check_release_assurance_workflow_artifact.py <path>`.
- [ ] `scripts/release_assurance.py` failure diagnostics are documented in `docs/security/release-assurance-diagnostics.md`, redact secrets/credentials, and support `--diagnostics-json`.
- [ ] `.github/workflows/release-assurance.yml` has an opt-in `upload_diagnostics_json` input defaulting to `false`, conditionally passes `--diagnostics-json`, and uploads a `release-assurance-diagnostics` artifact only on failure.
- [ ] `.github/workflows/release-assurance.yml` has an opt-in `validate_diagnostics_artifact` input defaulting to `false` and, when enabled, validates the diagnostics JSON with `scripts/check_release_assurance_diagnostics_artifact.py` before uploading the artifact.
- [ ] `scripts/check_release_assurance_diagnostics_workflow.py` passes.
- [ ] `python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q` passes.
- [ ] `scripts/check_release_assurance_diagnostics_artifact.py` exists and passes on a valid local diagnostics fixture.
- [ ] `python3.11 -m pytest tests/test_release_assurance_diagnostics_artifact.py -q` passes.
- [ ] Downloaded `release-assurance-diagnostics` artifacts (JSON file, extracted directory, or `.zip`) pass `python3.11 scripts/check_release_assurance_diagnostics_artifact.py <path> --expect-release <release>`.
- [ ] `.github/workflows/release-assurance-diagnostics-artifact-validate.yml` exists, is `workflow_dispatch` only, has `contents: read` and `actions: read` permissions, references no arbitrary secrets, and uses `GH_TOKEN: ${{ github.token }}`.
- [ ] `scripts/check_release_assurance_diagnostics_artifact_workflow.py` passes.
- [ ] `python3.11 -m pytest tests/test_release_assurance_diagnostics_artifact_workflow.py -q` passes.
- [ ] The diagnostics artifact revalidation workflow downloads a source artifact, validates it with `scripts/check_release_assurance_diagnostics_artifact.py`, uploads a `release-assurance-diagnostics-validation` report artifact, and fails if validation fails.
- [ ] Demo scripts and docs run locally without credentials, API keys, broker setup, network calls, or live trading enablement.
- [ ] Marketplace/outreach docs contain no profit, performance, live-trading-readiness, or autonomous-trading claims.
- [ ] `docs/autonomy-roadmap.md` clearly marks higher autonomy levels as future/out-of-scope and not implemented.
- [ ] No absolute user paths (home-directory or temp-folder prefixes) or credential examples appear in public demo or outreach docs.
- [ ] All demo/marketplace language remains paper-first, sandbox/preflight-first, broker-neutral, and safe-by-default.
- [ ] `docs/releases/v0.6.12-post-release-evidence.md` and `docs/releases/v0.6.12-post-release-evidence.json` exist and `python3.11 scripts/check_v0612_post_release_evidence.py` passes.
- [ ] `docs/releases/v0.6.12-candidate-readiness.md` exists as a historical planning record; `python3.11 scripts/check_v0612_release_candidate_readiness.py` still passes.
- [ ] `docs/releases/v0.6.13-plan.md` exists and is referenced as a planning-only document; it does not claim `v0.6.13` is released.
- [ ] `docs/releases/v0.6.13-candidate-selection.md` exists and `python3.11 scripts/check_v0613_post_release_hygiene.py` passes.
- [ ] `docs/releases/v0.6.13-paper-autonomy-evidence.md` and `.json` exist and `python3.11 scripts/check_v0613_paper_autonomy_evidence.py` passes.
- [ ] `python3.11 -m pytest tests/test_v0613_paper_autonomy_evidence.py -q` passes.
- [ ] `docs/releases/v0.6.14-paper-portfolio-evidence.md` and `.json` exist and `python3.11 scripts/check_v0614_paper_portfolio_evidence.py` passes.
- [ ] `docs/releases/v0.6.14-final-readiness-audit.md` and `.json` exist and `python3.11 scripts/check_v0614_final_readiness_audit.py` passes.
- [ ] `python3.11 -m pytest tests/test_v0614_final_readiness_audit.py -q` passes.
- [ ] `docs/releases/v0.6.14-post-release-evidence.md` and `.json` exist and `python3.11 scripts/check_v0614_post_release_hygiene.py` passes.
- [ ] `v0.6.14` is the current GitHub-only release, `v0.6.15` is planning-only, and PyPI remains unpublished.
- [ ] No active doc claims `v0.6.11` is the current public release.

### Autonomous paper workflow

- [ ] `docs/autonomous-paper-workflow.md` exists, links to `docs/bounded-live-autonomy-governance.md` and `docs/autonomy-roadmap.md`, and contains "paper-only", "not financial advice", and a statement that it does not claim autonomous-live-trading-readiness.
- [ ] `scripts/demo_autonomous_paper_workflow.sh` exists, is executable, uses `--mode paper --dry-run`, requires no credentials, and exits with code `0`.
- [ ] `scripts/check_autonomous_paper_workflow_demo.py` exists, passes, and supports `--json` output with `"passed": true`.
- [ ] `python3.11 -m pytest tests/test_autonomous_paper_workflow_demo.py -q` passes.
- [ ] Running `bash scripts/demo_autonomous_paper_workflow.sh` prints an "Autonomous paper workflow demo PASS" summary and produces only local, untracked evidence.
- [ ] Autonomous paper workflow docs, scripts, and tests contain no live-trading-readiness, profit, performance, or autonomous-live-trading claims.
- [ ] `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `.github/workflows/ci.yml` include the autonomous paper workflow checker and tests after the bounded autonomy governance checks.

### Paper strategy evaluation

- [ ] `docs/paper-strategy-evaluation.md` exists, links to paper/autonomy/safety docs, and states paper-only, no-provider/no-broker/no-network, not financial advice, no live readiness, and no profit guarantee.
- [ ] `scripts/demo_paper_strategy_evaluation.sh` exists, is executable, uses `atlas backtest compare`, requires no credentials, and exits with code `0`.
- [ ] `scripts/check_paper_strategy_evaluation.py` exists, passes, and supports `--json` output with `"passed": true`.
- [ ] `python3.11 -m pytest tests/test_paper_strategy_evaluation.py -q` passes.
- [ ] Running `bash scripts/demo_paper_strategy_evaluation.sh` prints a "Paper strategy evaluation demo PASS" summary and produces only local, untracked evidence.
- [ ] Paper strategy evaluation docs, scripts, and tests contain no live-trading-readiness, profit, performance, or autonomous-live-trading claims.
- [ ] `scripts/dev_check.sh`, `scripts/ci_check.sh`, `scripts/release_check.sh --quick`, and `.github/workflows/ci.yml` include the paper strategy evaluation checker and tests.

## Known limitations

- [ ] Final public release, not a release candidate
- [ ] Live trading explicitly disabled by default
- [ ] Provider execution remains locked for real providers
- [ ] Broker adapters in beta (Alpaca read-only sync available; others deferred)
- [ ] Dashboard is basic and read-only
- [ ] Backtesting is a research tool; historical results do not guarantee future performance
- [ ] Autonomous live trading is not supported and not a project goal

## Red flags to report

- Any claim that Atlas is ready for live trading or production trading
- Any claim of promised profitability, alpha verification, or market-beating performance
- Any request for real credentials in default verification flows
- Any staged package artifacts (`dist/`, `build/`, `*.egg-info/`)
- Any diff in protected boundaries (config, brokers, execution, safety, risk)
- Any absolute home or temp paths in public docs
