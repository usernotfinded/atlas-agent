# Paper Portfolio Reviewer Dossier and Evidence Bundle

## Status

v0.6.14 planning line. Paper-only. Offline/no-provider/no-broker/no-network.
No real notification sending. Not financial advice. Not live readiness.
Not a profit guarantee. Not production-ready.

## Purpose

Generate a deterministic paper-only reviewer dossier that bundles proposal, stress, monitoring, and recheck evidence into one stable human review packet.
Explain this is not live approval and not real allocation advice.
It does not submit orders, does not contact providers or brokers, does not send real notifications, and does not promote any strategy or portfolio to live trading or autonomous live trading.

## Inputs

- Paper portfolio proposal.
- Paper portfolio stress.
- Paper portfolio monitoring.
- Paper portfolio recheck ledger.
- A deterministic sample OHLCV fixture such as `data/sample/ohlcv_extended.csv`.

## Output Artifacts

The command writes untracked/generated artifacts to the requested output directory:

- JSON dossier: `paper-portfolio-dossier.json`
- Markdown dossier: `paper-portfolio-dossier.md`
- Evidence manifest JSON: `paper-portfolio-evidence-manifest.json`

## Dossier Decisions

- `paper_dossier_complete`: bundle complete; paper-only follow-up only.
- `paper_dossier_watchlist`: bundle requires extra watchlist monitoring.
- `paper_dossier_recheck_required`: bundle needs re-generation or more evidence.
- `paper_dossier_rejected`: bundle rejected based on paper guardrails.

Even `paper_dossier_complete` does NOT imply live readiness, production readiness,
or autonomous live trading readiness. It is not a profit guarantee and
does not imply future performance.

## Human Review Checklist

- Review paper-only allocation guardrails;
- Review stress constraints;
- Review monitoring/recheck triggers;
- Verify artifact consistency;
- Verify safety boundaries.

## Safety Boundaries

- No provider calls
- No broker calls
- No credentials
- No live trading
- No notifications sent
- No autonomous live trading readiness
- No production readiness claim
- No orders are generated
- No orders are submitted
- Review pass is not future-performance proof
- Review pass is not live-readiness or autonomous-live-readiness

## Relationship to v0.6.14 CAND-001/CAND-002/CAND-003/CAND-004

CAND-005 bundles the previous paper portfolio artifacts:

- [Paper Portfolio Proposal Sandbox](paper-portfolio-proposal.md)
- [Paper Portfolio Stress Constraints](paper-portfolio-stress.md)
- [Paper Portfolio Monitoring](paper-portfolio-monitoring.md)
- [Paper Portfolio Recheck Ledger and Human Review Queue](paper-portfolio-recheck-ledger.md)
