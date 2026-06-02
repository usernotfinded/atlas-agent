# Contributing to Atlas Agent

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Project Scope

Atlas Agent is a broker-neutral supervised trading workspace with market research, paper workflows, and deterministic risk gates. Contributions should align with the safe-by-default, sandbox-first design.

## Development Setup

```bash
# Install in editable mode with dev dependencies
python3.11 -m pip install -e '.[dev]'

# Run fast safety checks
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/verify_readme_quickstart.py
python3.11 scripts/check_public_docs_consistency.py

# Run dry-run checks (no artifacts created)
python3.11 scripts/check_clean_install.py --dry-run
python3.11 scripts/check_package_distribution.py --dry-run

# Run quick development gate
./scripts/release_check.sh --quick
```

## Branch/PR Expectations

- Work directly on `main` for small, scoped changes.
- For larger changes, use a feature branch.
- Keep PRs focused and surgical.
- Do not mix unrelated concerns in a single PR.

## Test Expectations

- Every new execution path must be tested.
- Run `./scripts/release_check.sh --quick` before submitting.
- For release-candidate readiness, run `./scripts/release_check.sh --full`.
- Do not weaken existing tests or remove forbidden-claim checks.

## Safety Boundaries

The following directories are **protected**. Changes to them require explicit justification and stricter review:

- `src/atlas_agent/config`
- `src/atlas_agent/brokers`
- `src/atlas_agent/execution`
- `src/atlas_agent/safety`
- `src/atlas_agent/risk`

Check protected boundary status before staging:

```bash
git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```

Expected: no output.

## Documentation Rules

- Public docs must not contain forbidden claims (examples of prohibited wording include assertions that live trading is ready or that profits are guaranteed).
- Public docs must not contain absolute paths (e.g., user home directories, system temp directories, or macOS private var paths).
- Public docs must include "not financial advice" wording.
- Do not add live trading instructions to the README.
- Do not add credential examples in public documentation.

## Forbidden Claims

Do not add the following claims anywhere in the repository. These categories of unsafe wording are prohibited:
- assertions that live trading is ready or production-ready
- assertions that trading is safe or without risk
- assertions that trust is granted or provider execution is enabled
- assertions that broker execution, orders, or approvals are enabled
- assertions that autonomous or real-money trading is ready
- assertions of guaranteed returns, profitable strategies, outperformance claims, or market-beating performance

## Protected Directories

See [Safety Boundaries](#safety-boundaries) above.

## How to Propose Changes

1. Open an issue using the appropriate template (bug report, feature request, docs issue, or safety concern).
2. For changes touching live trading, broker execution, provider execution, credentials, or risk gates, expect stricter review.
3. Keep changes minimal and well-justified.
4. Update docs if behavior or public interfaces change.

## How to Report Issues

Use the GitHub issue templates:
- **Bug report** — for reproducible defects
- **Feature request** — for new capabilities (with guardrails)
- **Docs issue** — for documentation problems or improvements
- **Safety concern** — for security, safety gate, or trust-boundary issues

## Contribution Rules

- Do not weaken safety tests.
- Do not remove forbidden-claim checks.
- Do not add credential examples.
- Do not add live trading instructions to the README.
- Do not add broker/provider execution behavior without dedicated review.
- Do not stage generated artifacts (`build/`, `dist/`, `*.egg-info/`, temp dirs, `.venv/`).

## Allowed Contribution Areas

- Documentation and public docs
- Tests and test infrastructure
- CLI UX and developer experience
- Safety validation and sandbox workflows
- Package and release engineering
- Non-execution research artifacts

Research-related contributions, including web research helpers, market data fixtures, and documentation around paper/sandbox workflows, must remain offline-safe, deterministic where practical, and must not imply trading correctness, profitability, live-trading readiness, or provider/broker execution approval.

## Stricter Review Required

Changes in the following areas require explicit justification and stricter review:
- Live trading enablement or gating
- Broker execution paths
- Provider execution unlocks
- Credential handling or secret loading
- Risk gate modifications
- Kill switch behavior
- Approval queue logic

Thank you for helping keep Atlas Agent safe by default.
