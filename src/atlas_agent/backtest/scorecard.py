# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/scorecard.py
# PURPOSE: Rolls evaluation, robustness, sensitivity and walk-forward into one
#          verdict a human can act on. The scorecard is what says "this strategy is
#          worth paper-trading" — it never says "worth trading live".
# DEPS:    backtest.evaluation, .robustness, .sensitivity, .walk_forward
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from atlas_agent.backtest.evaluation import build_paper_strategy_evaluation, parse_strategy_list
from atlas_agent.backtest.sensitivity import build_paper_strategy_sensitivity
from atlas_agent.backtest.robustness import build_paper_strategy_robustness, parse_fixture_list
from atlas_agent.backtest.walk_forward import build_paper_strategy_walk_forward

ARTIFACT_TYPE = "paper_strategy_scorecard"
SCHEMA_VERSION = 1
ALLOWED_SCORECARD_DECISIONS = (
    "paper_follow_up_candidate",
    "paper_watchlist",
    "needs_more_testing",
    "rejected",
)

def build_paper_strategy_scorecard(
    *,
    data_path: str | Path,
    symbol: str,
    fixtures: Iterable[str | Path] | None = None,
    strategies: Iterable[str] | None = None,
    window_size: int = 60,
    step_size: int = 30,
    initial_equity: float = 10000.0,
    slippage_bps: float = 0.0,
    commission_bps: float = 0.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    strategy_ids = list(strategies) if strategies is not None else parse_strategy_list(None)

    eval_report = build_paper_strategy_evaluation(
        data_path=data_path,
        symbol=symbol,
        strategies=strategy_ids,
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        start_date=start_date,
        end_date=end_date,
    )

    sens_report = build_paper_strategy_sensitivity(
        data_path=data_path,
        symbol=symbol,
        strategies=strategy_ids,
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        start_date=start_date,
        end_date=end_date,
    )

    wf_report = build_paper_strategy_walk_forward(
        data_path=data_path,
        symbol=symbol,
        window_size=window_size,
        step_size=step_size,
        strategies=strategy_ids,
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
    )

    rob_report = None
    if fixtures:
        rob_report = build_paper_strategy_robustness(
            fixture_paths=fixtures,
            symbol=symbol,
            strategies=strategy_ids,
            initial_equity=initial_equity,
            slippage_bps=slippage_bps,
            commission_bps=commission_bps,
            start_date=start_date,
            end_date=end_date,
        )

    entries = []
    ranking_inputs = []
    for strategy_id in strategy_ids:
        # Find results for this strategy in each report
        eval_res = next((s for s in eval_report.get("strategies", []) if s["name"] == strategy_id), None)
        sens_res = next((s for s in sens_report.get("strategies", []) if s["name"] == strategy_id), None)
        wf_res = next((s for s in wf_report.get("strategies", []) if s["name"] == strategy_id), None)
        rob_res = None
        if rob_report:
            rob_res = next((s for s in rob_report.get("strategies", []) if s["name"] == strategy_id), None)
        
        evidence = {
            "evaluation": {
                "status": "present" if eval_res else "missing",
                "summary": eval_res.get("paper_gate", {}).get("decision", "unknown") if eval_res else "unknown"
            },
            "sensitivity": {
                "status": "present" if sens_res else "missing",
                "summary": sens_res.get("sensitivity_summary", {}).get("paper_follow_up_status", "unknown") if sens_res else "unknown"
            },
            "walk_forward": {
                "status": "present" if wf_res else "missing",
                "summary": wf_res.get("walk_forward_summary", {}).get("paper_follow_up_status", "unknown") if wf_res else "unknown"
            },
            "robustness": {
                "status": "present" if rob_res else "missing",
                "summary": rob_res.get("robustness_summary", {}).get("paper_follow_up_status", "unknown") if rob_res else "unknown"
            }
        }
        
        decision, reason = _determine_scorecard_decision(evidence, has_robustness=bool(fixtures))
        
        entries.append({
            "name": strategy_id,
            "evidence": evidence,
            "scorecard": {
                "decision": decision,
                "reason": reason,
                "live_ready": False,
            }
        })

    # Sort entries by decision priority
    priority = {
        "paper_follow_up_candidate": 0,
        "paper_watchlist": 1,
        "needs_more_testing": 2,
        "rejected": 3
    }
    
    entries.sort(key=lambda x: (priority.get(x["scorecard"]["decision"], 3), x["name"]))
    
    ranking = []
    for i, entry in enumerate(entries, start=1):
        ranking.append({
            "rank": i,
            "strategy": entry["name"],
            "decision": entry["scorecard"]["decision"],
            "reason": entry["scorecard"]["reason"]
        })

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
        "symbol": symbol,
        "data_source": str(data_path),
        "evidence_streams": {
            "evaluation": True,
            "sensitivity": True,
            "walk_forward": True,
            "robustness": bool(fixtures)
        },
        "strategies": entries,
        "ranking": ranking,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True
        }
    }


def _determine_scorecard_decision(evidence: dict[str, Any], has_robustness: bool) -> tuple[str, str]:
    if evidence["evaluation"]["status"] != "present" or evidence["evaluation"]["summary"] == "rejected":
        return "rejected", "Base evaluation failed or is missing."
        
    if evidence["sensitivity"]["status"] != "present" or evidence["sensitivity"]["summary"] == "rejected":
        return "rejected", "Sensitivity evaluation failed or is missing."
        
    if evidence["walk_forward"]["status"] != "present" or evidence["walk_forward"]["summary"] == "rejected":
        return "rejected", "Walk-forward evaluation failed or is missing."
        
    if has_robustness:
        if evidence["robustness"]["status"] != "present" or evidence["robustness"]["summary"] == "rejected":
            return "rejected", "Robustness evaluation failed or is missing."

    # If anything needs more testing
    if evidence["evaluation"]["summary"] == "needs_more_testing" or \
       evidence["sensitivity"]["summary"] == "needs_more_testing" or \
       evidence["walk_forward"]["summary"] == "window_sensitive_needs_more_testing" or \
       (has_robustness and evidence["robustness"]["summary"] == "needs_more_testing"):
        return "needs_more_testing", "Evidence is inconclusive and requires more testing."

    # If anything is watchlist / sensitive
    if evidence["sensitivity"]["summary"] == "parameter_sensitive_needs_more_testing" or \
       (has_robustness and evidence["robustness"]["summary"] == "regime_sensitive_needs_more_testing"):
        return "paper_watchlist", "Strategy shows sensitivity to parameters or regimes; paper watchlist."

    # Otherwise candidate
    return "paper_follow_up_candidate", "Strong paper evidence across all dimensions. Approved for paper-only follow-up."


def write_strategy_scorecard_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "strategy-scorecard.json"
    markdown_path = destination / "strategy-scorecard.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_strategy_scorecard_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_strategy_scorecard_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Strategy Scorecard Report",
        "",
        (
            "**Status:** v0.6.13 planning line; paper-only; synthetic/sample-data only; "
            "offline/no-provider/no-broker; not financial advice; not live readiness; "
            "no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Data Source:** `{report['data_source']}`",
        "",
        (
            "This scorecard aggregates evidence from deterministic paper evaluations. "
            "It is for paper follow-up only. Candidate status does not imply future "
            "market performance and does not promote any strategy to live trading, "
            "autonomous live trading, or production use."
        ),
        "",
        "## Evidence Streams",
        "",
        "- **Evaluation:** " + ("Yes" if report["evidence_streams"].get("evaluation") else "No"),
        "- **Sensitivity:** " + ("Yes" if report["evidence_streams"].get("sensitivity") else "No"),
        "- **Robustness:** " + ("Yes" if report["evidence_streams"].get("robustness") else "No"),
        "- **Walk-Forward:** " + ("Yes" if report["evidence_streams"].get("walk_forward") else "No"),
        "",
        "## Strategy Matrix",
        "",
        "| Strategy | Eval | Sens | Robust | Walk-Fwd | Scorecard Decision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in report.get("strategies", []):
        lines.append(
            "| {name} | {eval} | {sens} | {rob} | {wf} | **{decision}** |".format(
                name=entry["name"],
                eval=entry["evidence"]["evaluation"]["summary"],
                sens=entry["evidence"]["sensitivity"]["summary"],
                rob=entry["evidence"]["robustness"]["summary"],
                wf=entry["evidence"]["walk_forward"]["summary"],
                decision=entry["scorecard"]["decision"],
            )
        )

    lines.extend(["", "## Ranking", ""])
    for ranked in report.get("ranking", []):
        lines.append(f"{ranked['rank']}. `{ranked['strategy']}`: **{ranked['decision']}** - {ranked['reason']}")

    lines.extend(
        [
            "",
            "## Scorecard Decisions",
            "",
            "- `paper_follow_up_candidate`: strong evidence across all streams; paper-only follow-up.",
            "- `paper_watchlist`: mixed valid results suggest sensitivity; merits tracking.",
            "- `needs_more_testing`: evidence is insufficient or inconclusive.",
            "- `rejected`: hard failures or blockers in one or more streams.",
            "",
            "No decision is an approval for live trading.",
            "",
            "## Safety",
            "",
            "- No provider calls.",
            "- No broker calls.",
            "- No credentials.",
            "- No live trading.",
            "- No autonomous live trading readiness.",
            "",
        ]
    )
    return "\n".join(lines)
