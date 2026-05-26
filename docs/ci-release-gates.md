# CI Release Gates

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What the CI checks

Atlas Agent uses GitHub Actions to enforce release-quality checks on every pull request and push to `main`. The CI is split into two tiers to balance speed and thoroughness.

### Quick Gate (pull_request / push to main)

The quick gate runs fast, safe checks that complete in a few minutes. It does not run heavy demos or the full pytest suite.

Steps:

1. **Install package and test dependencies**
2. **Version consistency** — `scripts/check_version_consistency.py`
3. **Forbidden claims scan** — `scripts/check_forbidden_claims.py`
4. **Public docs consistency** — `scripts/check_public_docs_consistency.py`
5. **README quickstart verification** — `scripts/verify_readme_quickstart.py`
6. **RC cutover check** — `scripts/check_rc1_cutover.py`
7. **Clean install dry-run** — `scripts/check_clean_install.py --dry-run`
8. **Clean install verification** — `scripts/check_clean_install.py`
9. **Package distribution dry-run** — `scripts/check_package_distribution.py --dry-run`
10. **Package distribution verification** — `scripts/check_package_distribution.py`
11. **Focused pytest subset**:
    - `tests/test_clean_install_check.py`
    - `tests/test_package_distribution_check.py`
    - `tests/test_rc1_cutover_consistency.py`
    - `tests/test_changelog_consistency.py`
    - `tests/test_public_docs_consistency.py`
    - `tests/test_readme_quickstart_verification.py`
    - `tests/test_release_check_scripts.py`
    - `tests/test_ci_workflows.py`
    - `tests/test_docs_v040.py`
12. **pip check**
13. **git diff --check**
14. **Protected staged files check** — `scripts/check_no_protected_staged.py`

### Heavy Release Gate (workflow_dispatch / tags)

The heavy gate runs full validation including demos and the complete pytest suite. It is triggered manually or on tags to avoid slowing down every PR.

Steps:

1. **Install package and test dependencies**
2. **Release check quick** — `./scripts/release_check.sh --quick`
3. **Release check research** — `./scripts/release_check.sh --research`
4. **Release check full** — `./scripts/release_check.sh --full`
5. **Clean install verification** — `scripts/check_clean_install.py`
6. **Package distribution verification** — `scripts/check_package_distribution.py`

### Research Path-Filtered Gate (push/PR on research paths)

Runs when research-related files change:

- `./scripts/release_check.sh --research`

### Atlas Paper Routines (scheduled)

Scheduled paper-mode routine runs. See `.github/workflows/atlas-routines.yml`.

## What CI does not do

- **Does not publish** to PyPI.
- **Does not upload** packages anywhere.
- **Does not create** GitHub releases.
- **Does not push** tags.
- **Does not require** broker/provider credentials.
- **Does not require** OpenAI API keys or other secrets.
- **Does not enable** live trading.
- **Does not call** live providers or brokers.

## Safety rules

- No secrets referenced in workflow files.
- No `TWINE_USERNAME`, `TWINE_PASSWORD`, `PYPI_API_TOKEN`, `OPENAI_API_KEY`, or broker API keys.
- No `gh release create`, `twine upload`, `git push`, or `git tag` commands.
- Atlas runtime tests remain local-only and do not call external APIs.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.
- No broker/order path in CI.
- No credentials loaded by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## Why full gates are manual

The full pytest suite plus demo workflows can take 15+ minutes. Running this on every PR would slow down development. The quick gate catches the most common issues fast, while the heavy gate is available for manual validation before tagging or releasing.

## Local CI parity

Run the local CI parity helper to mirror the quick gate:

```bash
./scripts/ci_check.sh
```

For the heavy gate, run:

```bash
./scripts/release_check.sh --full
```
