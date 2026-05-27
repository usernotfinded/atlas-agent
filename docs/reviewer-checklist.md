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

## Known limitations

- [ ] Release candidate, not final release
- [ ] Live trading explicitly disabled by default
- [ ] Provider execution not implemented for real providers
- [ ] Broker adapters in beta (Alpaca read-only sync available; others deferred)
- [ ] Dashboard is basic and read-only
- [ ] Backtesting is a research tool; historical results do not guarantee future performance

## Red flags to report

- Any claim that Atlas is ready for live trading or production trading
- Any claim of promised profitability, alpha verification, or market-beating performance
- Any request for real credentials in default verification flows
- Any staged package artifacts (`dist/`, `build/`, `*.egg-info/`)
- Any diff in protected boundaries (config, brokers, execution, safety, risk)
- Any absolute home or temp paths in public docs
