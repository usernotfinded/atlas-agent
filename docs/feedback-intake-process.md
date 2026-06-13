# Public Feedback Intake Process

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What feedback is wanted

We welcome structured technical feedback from external reviewers, local-first developers, Python CLI maintainers, OSS release engineers, and safety/audit reviewers. Useful categories include:

- **Install friction** — did `pip install -e .` work cleanly?
- **Docs clarity** — is the README accurate? Can a new visitor understand what Atlas is and is not?
- **CLI UX** — are commands named clearly? Is help text useful?
- **Safety model** — is it obvious what is disabled by default?
- **Research workflow** — do the paper-only research commands work without credentials?
- **Test / release gates** — is the quick/research/full gate structure reasonable?
- **Bug reports** — reproducible defects in local-only paths.

## What feedback is out of scope

The following are **not accepted** and will be closed without action:

- Requests to bypass safety gates or approval workflows
- Requests to enable live trading by default
- Requests for profit guarantees or trading performance evaluations
- Requests for trading signal quality assessment
- Requests for real-money broker setup tutorials
- Credential sharing or "help me connect my broker" requests

## Pre-feedback checks

Before opening feedback, please run the safe local checks:

```bash
python3.11 scripts/smoke_reviewer_golden_path.py
python3.11 scripts/build_release_evidence_bundle.py --skip-slow
python3.11 scripts/check_cli_command_compatibility.py
```

If any of these fail on your environment, include the output (with secrets and absolute paths removed) in your feedback.

## How to submit feedback

Use the GitHub issue templates:

- **[Reviewer Feedback](https://github.com/usernotfinded/atlas-agent/issues/new?template=reviewer_feedback.yml)** — structured technical feedback
- **[Bug Report](https://github.com/usernotfinded/atlas-agent/issues/new?template=bug_report.yml)** — reproducible defects
- **[Docs Issue](https://github.com/usernotfinded/atlas-agent/issues/new?template=docs_issue.yml)** — documentation problems
- **[Safety Concern](https://github.com/usernotfinded/atlas-agent/issues/new?template=safety_concern.yml)** — safety gate or trust-boundary issues
- **[Feature Request](https://github.com/usernotfinded/atlas-agent/issues/new?template=feature_request.yml)** — capability suggestions

For active credential leaks or security vulnerabilities, use [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories) instead.

## Maintainer triage process

Incoming feedback is triaged within a few business days:

1. **Auto-label** by template type (`feedback`, `bug`, `docs`, `safety`, `enhancement`).
2. **Safety scan** — check for credential leaks, absolute paths, or unsafe requests. Remove or redact if found.
3. **Blocker assessment** — classify as blocker or non-blocker:
   - **Blocker** — affects install, breaks deterministic checks, or weakens safety wording.
   - **Non-blocker** — docs clarity, UX polish, or enhancement ideas.
4. **Map to milestone** — blocker issues are candidates for the current planning milestone (e.g., `v0.6.10`); non-blockers are backlog.
5. **Close out-of-scope** — requests for live trading enablement, profit evaluation, or safety bypass are closed with a reference to this policy.

## Labels and categories

| Label | Meaning |
|---|---|
| `feedback` | General reviewer feedback |
| `bug` | Reproducible defect |
| `docs` | Documentation issue |
| `safety` | Safety gate or trust-boundary concern |
| `security` | Security vulnerability |
| `enhancement` | Feature request |
| `blocker` | Must fix before next release |
| `non-blocker` | Nice to have, backlog |

## Blocker vs non-blocker classification

**Blocker criteria:**
- Breaks the reviewer golden-path smoke test on a clean environment
- Introduces forbidden claims or overstatements in public docs
- Weakens safety gates or makes live/provider/broker paths easier to activate
- Leaks credentials or absolute paths in public artifacts

**Non-blocker criteria:**
- README wording improvements
- CLI help text clarifications
- Additional check scripts or test coverage
- Refactoring suggestions that preserve behavior

## Safety-sensitive reports

Safety and security reports are treated as high priority:

- Do not dismiss concerns because "live trading is disabled."
- Evaluate impact on paper/sandbox workflows and docs integrity.
- Document resolved issues in `SECURITY.md` and changelog if appropriate.
- For private disclosure, use GitHub Security Advisories.

## Mapping feedback to current planning work

Feedback that meets blocker criteria is triaged into the current planning milestone (e.g., `v0.6.10`). Typical planning work includes:

- Post-release CLI refactor regression fixes
- New check scripts and compatibility contracts
- Docs honesty and clarity improvements
- Release engineering automation

Out-of-scope requests are closed and documented as "not planned."

## Avoiding profitability and real-money claims

Maintainers must not:

- Accept feedback that implies Atlas is profitable or "beats the market."
- Create issues from requests to evaluate trading signal quality.
- Respond to "is this safe to trade live?" with anything other than a reference to the safety docs and disclaimer.
- Treat broker setup or credential configuration as a supported use case for public feedback.

## Safety summary

- Live trading disabled by default.
- Provider execution remains locked.
- Broker execution remains blocked unless explicit opt-in gates pass.
- No credentials required for default verification.
- Not financial advice. Does not imply profitability or trading correctness.
