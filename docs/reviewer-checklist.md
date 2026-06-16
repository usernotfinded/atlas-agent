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

## Package checks

- [ ] `scripts/check_package_distribution.py --dry-run` passes
- [ ] Package distribution dry-run does not publish or upload
- [ ] Clean install check passes or dry-run passes

## Provider safety workflow

- [ ] Provider safety dossier is described as sandbox-only and offline
- [ ] No broker/order path in provider safety workflows
- [ ] No credentials loaded by default in safety workflows

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
- [ ] Demo scripts and docs run locally without credentials, API keys, broker setup, network calls, or live trading enablement.
- [ ] Marketplace/outreach docs contain no profit, performance, live-trading-readiness, or autonomous-trading claims.
- [ ] `docs/autonomy-roadmap.md` clearly marks higher autonomy levels as future/out-of-scope and not implemented.
- [ ] No absolute user paths (home-directory or temp-folder prefixes) or credential examples appear in public demo or outreach docs.
- [ ] All demo/marketplace language remains paper-first, sandbox/preflight-first, broker-neutral, and safe-by-default.

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
