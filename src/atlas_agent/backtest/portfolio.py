from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

from atlas_agent.backtest.scorecard import build_paper_strategy_scorecard

ARTIFACT_TYPE = "paper_portfolio_proposal"
STRESS_ARTIFACT_TYPE = "paper_portfolio_stress"
SCHEMA_VERSION = 1
ALLOWED_STRESS_STATUSES = {
    "paper_stress_pass",
    "paper_stress_watchlist",
    "needs_more_testing",
    "rejected",
}
STRESS_SCENARIOS = (
    "flash_crash",
    "volatility_spike",
    "liquidity_gap",
    "sideways_chop",
    "slow_drawdown",
)
MONITORING_ARTIFACT_TYPE = "paper_portfolio_monitoring"
ALLOWED_MONITORING_STATUSES = {
    "paper_monitor_ok",
    "paper_monitor_watchlist",
    "needs_recheck",
    "rejected",
}
MONITORING_TRIGGER_TYPES = (
    "allocation_drift",
    "cash_reserve_breach",
    "drawdown_breach",
    "stress_watchlist",
    "stale_artifact",
    "insufficient_data",
)

def build_paper_portfolio_proposal(
    *,
    data_path: str | Path,
    symbol: str,
    strategies: Iterable[str] | None = None,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    window_size: int = 60,
    step_size: int = 30,
    initial_equity: float = 10000.0,
    slippage_bps: float = 0.0,
    commission_bps: float = 0.0,
) -> dict[str, Any]:
    scorecard = build_paper_strategy_scorecard(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        window_size=window_size,
        step_size=step_size,
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
    )

    allocations = []
    excluded = []
    
    candidates = [
        s for s in scorecard["ranking"] 
        if s["decision"] == "paper_follow_up_candidate"
    ]
    watchlist = [
        s for s in scorecard["ranking"]
        if s["decision"] == "paper_watchlist"
    ]
    rejected = [
        s for s in scorecard["ranking"]
        if s["decision"] in ("rejected", "needs_more_testing")
    ]

    total_alloc = 0.0
    
    if not candidates and not watchlist:
        proposal_status = "needs_more_testing"
        allocations.append({
            "strategy": "cash",
            "paper_weight": 1.0,
            "reason": "minimum paper cash reserve / no eligible candidates"
        })
        for r in scorecard["ranking"]:
            excluded.append({
                "strategy": r["strategy"],
                "reason": r["reason"]
            })
    else:
        proposal_status = "paper_portfolio_proposal"
        if not candidates and watchlist:
            proposal_status = "paper_watchlist_portfolio"
            
        eligible = candidates + watchlist
        target_weight_per_strategy = (1.0 - min_cash_weight) / len(eligible)
        assigned_weight = min(max_strategy_weight, target_weight_per_strategy)
        
        for e in eligible:
            allocations.append({
                "strategy": e["strategy"],
                "scorecard_decision": e["decision"],
                "paper_weight": assigned_weight,
                "reason": e["reason"]
            })
            total_alloc += assigned_weight
        
        cash_weight = 1.0 - total_alloc
        allocations.append({
            "strategy": "cash",
            "paper_weight": cash_weight,
            "reason": "minimum paper cash reserve"
        })
        
        for r in rejected:
            excluded.append({
                "strategy": r["strategy"],
                "reason": r["reason"]
            })

    allocations.sort(key=lambda x: (x["strategy"] != "cash", -x["paper_weight"], x["strategy"]))

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
        "proposal_status": proposal_status,
        "allocation_rules": {
            "max_strategy_weight": max_strategy_weight,
            "min_cash_weight": min_cash_weight,
            "rejected_strategy_weight": 0.0
        },
        "allocations": allocations,
        "excluded": excluded,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True
        }
    }

def write_portfolio_proposal_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "paper-portfolio-proposal.json"
    markdown_path = destination / "paper-portfolio-proposal.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_portfolio_proposal_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def build_paper_portfolio_stress(
    *,
    data_path: str | Path,
    symbol: str,
    strategies: Iterable[str] | None = None,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    max_stressed_drawdown: float = 0.25,
    max_single_scenario_loss: float = 0.20,
    proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic paper-only stress report for a portfolio proposal."""
    proposal_report = proposal or build_paper_portfolio_proposal(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
    )
    allocations = proposal_report.get("allocations", [])
    stress_constraints = {
        "max_stressed_drawdown": max_stressed_drawdown,
        "max_single_scenario_loss": max_single_scenario_loss,
        "max_strategy_weight": max_strategy_weight,
        "min_cash_weight": min_cash_weight,
    }
    constraint_findings = _validate_stress_constraints(
        allocations=allocations,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
    )
    base_returns = _load_close_returns(data_path)
    scenarios = _build_stress_scenarios(base_returns)
    stress_results = [
        _evaluate_stress_scenario(
            scenario=name,
            returns=returns,
            allocations=allocations,
            max_stressed_drawdown=max_stressed_drawdown,
            max_single_scenario_loss=max_single_scenario_loss,
            proposal_status=proposal_report.get("proposal_status", "needs_more_testing"),
            constraint_findings=constraint_findings,
        )
        for name, returns in scenarios.items()
    ]
    overall_stress_status = _overall_stress_status(stress_results, constraint_findings)
    return {
        "artifact_type": STRESS_ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
        "symbol": symbol,
        "data_source": str(data_path),
        "proposal_source": "generated" if proposal is None else "provided",
        "stress_constraints": stress_constraints,
        "proposal": {
            "status": proposal_report.get("proposal_status", "needs_more_testing"),
            "allocations": allocations,
            "excluded": proposal_report.get("excluded", []),
        },
        "constraint_findings": constraint_findings,
        "stress_results": stress_results,
        "overall_stress_status": overall_stress_status,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
            "paper_only": True,
        },
    }


def write_portfolio_stress_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "paper-portfolio-stress.json"
    markdown_path = destination / "paper-portfolio-stress.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_portfolio_stress_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_portfolio_stress_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Portfolio Stress Report",
        "",
        (
            "**Status:** v0.6.14 planning line; paper-only; synthetic/sample stress only; "
            "offline/no-provider/no-broker/no-network; not financial advice; not live readiness; "
            "no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Data Source:** `{report['data_source']}`",
        f"**Overall Stress Status:** `{report['overall_stress_status']}`",
        "",
        (
            "This report applies deterministic paper-only stress constraints to a paper "
            "portfolio proposal. It does not submit orders, does not contact providers or "
            "brokers, does not prove future performance, and does not promote any strategy "
            "or portfolio to live trading or autonomous live trading."
        ),
        "",
        "## Stress Constraints",
        "",
    ]
    for key, value in report["stress_constraints"].items():
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "## Proposal Allocations",
        "",
        "| Strategy | Weight | Decision | Reason |",
        "| --- | --- | --- | --- |",
    ])
    for alloc in report["proposal"]["allocations"]:
        decision = alloc.get("scorecard_decision", "N/A")
        lines.append(f"| {alloc['strategy']} | {alloc['paper_weight']:.4f} | {decision} | {alloc['reason']} |")

    lines.extend([
        "",
        "## Stress Results",
        "",
        "| Scenario | Stressed Return | Stressed Drawdown | Status | Reason |",
        "| --- | ---: | ---: | --- | --- |",
    ])
    for result in report["stress_results"]:
        lines.append(
            "| {scenario} | {ret:.4f} | {drawdown:.4f} | `{status}` | {reason} |".format(
                scenario=result["scenario"],
                ret=result["stressed_return"],
                drawdown=result["stressed_drawdown"],
                status=result["status"],
                reason=result["reason"],
            )
        )

    lines.extend([
        "",
        "## Safety Boundaries",
        "",
        "- Paper-only and offline.",
        "- Synthetic/sample stress only.",
        "- No provider calls, broker calls, credentials, network calls, or live orders.",
        "- Stress pass is not future-performance proof.",
        "- Stress pass is not live-readiness or autonomous-live-readiness.",
        "",
    ])
    return "\n".join(lines)


def _load_close_returns(data_path: str | Path) -> list[float]:
    path = Path(data_path)
    closes: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                closes.append(float(row["close"]))
            except (KeyError, TypeError, ValueError):
                continue
    returns: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous > 0:
            returns.append((current / previous) - 1.0)
    return returns or [0.0]


def _build_stress_scenarios(base_returns: list[float]) -> dict[str, list[float]]:
    sample = (base_returns[:30] or [0.0])
    return {
        "flash_crash": [-0.03, -0.06, -0.09, -0.04, 0.015, 0.01, -0.01, 0.005],
        "volatility_spike": [
            (0.035 if index % 2 else -0.04) + max(min(value, 0.02), -0.02)
            for index, value in enumerate(sample[:16])
        ],
        "liquidity_gap": [-0.12, -0.025, 0.0, 0.004, 0.006, -0.01, 0.003, 0.002],
        "sideways_chop": [
            0.012 if index % 2 else -0.012
            for index, _ in enumerate(sample[:20])
        ],
        "slow_drawdown": [-0.012 for _ in range(24)],
    }


def _validate_stress_constraints(
    *,
    allocations: list[dict[str, Any]],
    max_strategy_weight: float,
    min_cash_weight: float,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    weights = [_clean_weight(item.get("paper_weight")) for item in allocations]
    total_weight = sum(weights)
    if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=0.001):
        findings.append({
            "constraint": "weights_sum_to_one",
            "status": "rejected",
            "reason": f"Paper weights sum to {total_weight:.6f}, not 1.0.",
        })
    cash_weight = sum(
        _clean_weight(item.get("paper_weight"))
        for item in allocations
        if item.get("strategy") == "cash"
    )
    if cash_weight + 0.000001 < min_cash_weight:
        findings.append({
            "constraint": "min_cash_weight",
            "status": "rejected",
            "reason": f"Cash weight {cash_weight:.6f} is below {min_cash_weight:.6f}.",
        })
    for item in allocations:
        strategy = str(item.get("strategy", "unknown"))
        weight = _clean_weight(item.get("paper_weight"))
        if strategy != "cash" and weight > max_strategy_weight + 0.000001:
            findings.append({
                "constraint": "max_strategy_weight",
                "status": "rejected",
                "strategy": strategy,
                "reason": f"{strategy} weight {weight:.6f} exceeds {max_strategy_weight:.6f}.",
            })
        if item.get("scorecard_decision") in {"rejected", "needs_more_testing"} and weight > 0:
            findings.append({
                "constraint": "rejected_strategies_excluded",
                "status": "rejected",
                "strategy": strategy,
                "reason": f"{strategy} has positive weight despite non-eligible scorecard decision.",
            })
    return findings


def _evaluate_stress_scenario(
    *,
    scenario: str,
    returns: list[float],
    allocations: list[dict[str, Any]],
    max_stressed_drawdown: float,
    max_single_scenario_loss: float,
    proposal_status: str,
    constraint_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    portfolio_returns = []
    contributions = [
        {
            "strategy": item.get("strategy", "unknown"),
            "weight": _clean_weight(item.get("paper_weight")),
            "stress_beta": _stress_beta(str(item.get("strategy", ""))),
        }
        for item in allocations
    ]
    for scenario_return in returns:
        portfolio_return = 0.0
        for item in contributions:
            if item["strategy"] == "cash":
                continue
            portfolio_return += item["weight"] * item["stress_beta"] * scenario_return
        portfolio_returns.append(portfolio_return)
    stressed_return, stressed_drawdown = _return_and_drawdown(portfolio_returns)
    status, reason = _scenario_status(
        stressed_return=stressed_return,
        stressed_drawdown=stressed_drawdown,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        proposal_status=proposal_status,
        has_constraint_findings=bool(constraint_findings),
    )
    return {
        "scenario": scenario,
        "stressed_return": round(stressed_return, 6),
        "stressed_drawdown": round(stressed_drawdown, 6),
        "status": status,
        "reason": reason,
        "strategy_contributions": [
            {
                "strategy": item["strategy"],
                "paper_weight": item["weight"],
                "stress_beta": item["stress_beta"],
                "scenario_loss_attribution": round(
                    min(0.0, item["weight"] * item["stress_beta"] * stressed_return),
                    6,
                ),
            }
            for item in contributions
            if item["strategy"] != "cash"
        ],
    }


def _scenario_status(
    *,
    stressed_return: float,
    stressed_drawdown: float,
    max_stressed_drawdown: float,
    max_single_scenario_loss: float,
    proposal_status: str,
    has_constraint_findings: bool,
) -> tuple[str, str]:
    if has_constraint_findings:
        return "rejected", "Hard allocation constraint failed before scenario evaluation."
    if proposal_status in {"needs_more_testing", "rejected"}:
        return "needs_more_testing", "Proposal evidence is insufficient for a paper stress pass."
    if stressed_drawdown > max_stressed_drawdown:
        return "rejected", "Stressed drawdown breached the paper-only guardrail."
    if stressed_return < -max_single_scenario_loss:
        return "rejected", "Single-scenario loss breached the paper-only guardrail."
    if (
        stressed_drawdown > max_stressed_drawdown * 0.80
        or stressed_return < -(max_single_scenario_loss * 0.80)
    ):
        return "paper_stress_watchlist", "Scenario is within hard limits but near a paper-only guardrail."
    return "paper_stress_pass", "Scenario stayed within paper-only stress guardrails."


def _overall_stress_status(
    stress_results: list[dict[str, Any]],
    constraint_findings: list[dict[str, Any]],
) -> str:
    if constraint_findings:
        return "rejected"
    statuses = {item["status"] for item in stress_results}
    if "rejected" in statuses:
        return "rejected"
    if "needs_more_testing" in statuses:
        return "needs_more_testing"
    if "paper_stress_watchlist" in statuses:
        return "paper_stress_watchlist"
    return "paper_stress_pass"


def _return_and_drawdown(returns: list[float]) -> tuple[float, float]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for daily_return in returns:
        equity *= max(0.0, 1.0 + daily_return)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return equity - 1.0, max_drawdown


def _stress_beta(strategy: str) -> float:
    betas = {
        "buy_and_hold": 1.00,
        "moving_average_cross": 0.80,
        "rsi_mean_reversion": 0.65,
        "cash": 0.0,
    }
    return betas.get(strategy, 0.90)


def _clean_weight(value: Any) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(weight):
        return 0.0
    return weight


def render_portfolio_proposal_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Portfolio Proposal Report",
        "",
        (
            "**Status:** v0.6.14 planning line; paper-only; synthetic/sample-data only; "
            "offline/no-provider/no-broker; not financial advice; not live readiness; "
            "no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Data Source:** `{report['data_source']}`",
        f"**Proposal Status:** `{report['proposal_status']}`",
        "",
        (
            "This proposal translates paper scorecard evidence into conservative paper-only "
            "allocation sandbox limits. It is for paper simulation only. The allocation does "
            "not imply future market performance, does not submit any real orders, and does "
            "not promote any strategy or portfolio to live trading or autonomous live trading."
        ),
        "",
        "## Allocation Rules",
        "",
        f"- Max Strategy Weight: {report['allocation_rules']['max_strategy_weight']}",
        f"- Min Cash Weight: {report['allocation_rules']['min_cash_weight']}",
        f"- Rejected Strategy Weight: {report['allocation_rules']['rejected_strategy_weight']}",
        "",
        "## Proposed Allocations",
        "",
        "| Strategy | Weight | Decision | Reason |",
        "| --- | --- | --- | --- |",
    ]

    for alloc in report["allocations"]:
        decision = alloc.get("scorecard_decision", "N/A")
        lines.append(f"| {alloc['strategy']} | {alloc['paper_weight']:.4f} | {decision} | {alloc['reason']} |")

    lines.extend([
        "",
        "## Excluded Strategies",
        "",
        "| Strategy | Reason |",
        "| --- | --- |",
    ])
    
    if not report["excluded"]:
        lines.append("| None | N/A |")
    else:
        for ex in report["excluded"]:
            lines.append(f"| {ex['strategy']} | {ex['reason']} |")

    lines.append("")
    return "\\n".join(lines) + "\\n"


def build_paper_portfolio_monitoring(
    *,
    data_path: str | Path,
    symbol: str,
    strategies: Iterable[str] | None = None,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    max_stressed_drawdown: float = 0.25,
    max_single_scenario_loss: float = 0.20,
    monitor_window: int = 20,
    recheck_threshold: float = 0.05,
    proposal: dict[str, Any] | None = None,
    stress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic paper-only portfolio monitoring simulation.

    This consumes/generates paper portfolio proposal and stress artifacts,
    then simulates recheck/watchlist behaviour over bundled/sample data
    monitoring windows.  No provider, broker, network, or live trading
    path is used.
    """
    proposal_report = proposal or build_paper_portfolio_proposal(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
    )
    stress_report = stress or build_paper_portfolio_stress(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        proposal=proposal_report,
    )
    base_returns = _load_close_returns(data_path)
    monitoring_rules = {
        "monitor_window": monitor_window,
        "recheck_threshold": recheck_threshold,
        "min_cash_weight": min_cash_weight,
        "max_strategy_weight": max_strategy_weight,
    }
    monitoring_events = _simulate_monitoring_windows(
        base_returns=base_returns,
        allocations=proposal_report.get("allocations", []),
        proposal_status=proposal_report.get("proposal_status", "needs_more_testing"),
        stress_status=stress_report.get("overall_stress_status", "needs_more_testing"),
        monitor_window=monitor_window,
        recheck_threshold=recheck_threshold,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
    )
    overall_status = _overall_monitoring_status(monitoring_events)
    human_review = overall_status != "paper_monitor_ok"
    return {
        "artifact_type": MONITORING_ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
        "symbol": symbol,
        "data_source": str(data_path),
        "proposal_source": "provided" if proposal is not None else "generated",
        "stress_source": "provided" if stress is not None else "generated",
        "monitoring_rules": monitoring_rules,
        "monitoring_events": monitoring_events,
        "overall_monitoring_status": overall_status,
        "human_review_recommended": human_review,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_notifications_sent": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
        },
    }


def write_portfolio_monitoring_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "paper-portfolio-monitoring.json"
    markdown_path = destination / "paper-portfolio-monitoring.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_portfolio_monitoring_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_portfolio_monitoring_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Portfolio Monitoring Simulation Report",
        "",
        (
            "**Status:** v0.6.14 planning line; paper-only; synthetic/sample monitoring "
            "simulation only; offline/no-provider/no-broker/no-network; not financial advice; "
            "not live readiness; no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Data Source:** `{report['data_source']}`",
        f"**Proposal Source:** {report['proposal_source']}",
        f"**Stress Source:** {report['stress_source']}",
        f"**Overall Monitoring Status:** `{report['overall_monitoring_status']}`",
        f"**Human Review Recommended:** {report['human_review_recommended']}",
        "",
        (
            "This report simulates paper-only monitoring windows over local sample data. "
            "It does not submit orders, does not contact providers or brokers, does not "
            "send real notifications, does not prove future performance, and does not "
            "promote any strategy or portfolio to live trading or autonomous live trading."
        ),
        "",
        "## Monitoring Rules",
        "",
    ]
    for key, value in report["monitoring_rules"].items():
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "## Monitoring Events",
        "",
        "| Window | Trigger | Status | Reason |",
        "| ---: | --- | --- | --- |",
    ])
    for event in report["monitoring_events"]:
        lines.append(
            "| {window} | {trigger} | `{status}` | {reason} |".format(
                window=event["window"],
                trigger=event["trigger"],
                status=event["status"],
                reason=event["reason"],
            )
        )

    lines.extend([
        "",
        "## Safety Boundaries",
        "",
        "- Paper-only and offline.",
        "- Synthetic/sample monitoring simulation only.",
        "- No provider calls, broker calls, credentials, network calls, or live orders.",
        "- No real notifications are sent.",
        "- Monitoring pass is not future-performance proof.",
        "- Monitoring pass is not live-readiness or autonomous-live-readiness.",
        "- No orders are submitted.",
        "",
    ])
    return "\n".join(lines)


def _simulate_monitoring_windows(
    *,
    base_returns: list[float],
    allocations: list[dict[str, Any]],
    proposal_status: str,
    stress_status: str,
    monitor_window: int,
    recheck_threshold: float,
    max_strategy_weight: float,
    min_cash_weight: float,
    max_stressed_drawdown: float,
) -> list[dict[str, Any]]:
    """Generate deterministic monitoring events across sliding windows."""
    events: list[dict[str, Any]] = []
    total_periods = len(base_returns)
    window_idx = 0

    # Check for insufficient data
    if total_periods < monitor_window:
        events.append({
            "window": 0,
            "trigger": "insufficient_data",
            "status": "needs_recheck",
            "reason": f"Only {total_periods} return periods available; need {monitor_window}.",
        })
        return events

    # Check for invalid proposal/stress status
    if proposal_status in {"rejected", "needs_more_testing"}:
        events.append({
            "window": 0,
            "trigger": "stale_artifact",
            "status": "rejected" if proposal_status == "rejected" else "needs_recheck",
            "reason": f"Proposal status is '{proposal_status}'; monitoring requires an eligible proposal.",
        })
        return events

    if stress_status == "rejected":
        events.append({
            "window": 0,
            "trigger": "stale_artifact",
            "status": "rejected",
            "reason": "Stress status is 'rejected'; monitoring requires a non-rejected stress report.",
        })
        return events

    # Simulate sliding windows over available returns
    start = 0
    while start + monitor_window <= total_periods:
        window_idx += 1
        window_returns = base_returns[start:start + monitor_window]

        # 1. allocation drift check
        events.append(_check_allocation_drift(
            window=window_idx,
            window_returns=window_returns,
            allocations=allocations,
            recheck_threshold=recheck_threshold,
        ))

        # 2. cash reserve check
        events.append(_check_cash_reserve(
            window=window_idx,
            allocations=allocations,
            min_cash_weight=min_cash_weight,
        ))

        # 3. drawdown breach check
        events.append(_check_drawdown_breach(
            window=window_idx,
            window_returns=window_returns,
            allocations=allocations,
            max_stressed_drawdown=max_stressed_drawdown,
        ))

        # 4. stress watchlist check
        events.append(_check_stress_watchlist(
            window=window_idx,
            stress_status=stress_status,
        ))

        start += monitor_window

    return events


def _check_allocation_drift(
    *,
    window: int,
    window_returns: list[float],
    allocations: list[dict[str, Any]],
    recheck_threshold: float,
) -> dict[str, Any]:
    """Check whether simulated allocation drift exceeds the recheck threshold."""
    cumulative = 1.0
    for r in window_returns:
        cumulative *= max(0.0, 1.0 + r)
    drift = abs(cumulative - 1.0)
    if drift > recheck_threshold * 2:
        return {
            "window": window,
            "trigger": "allocation_drift",
            "status": "paper_monitor_watchlist",
            "reason": f"Simulated drift {drift:.4f} exceeds 2x recheck threshold {recheck_threshold * 2:.4f}.",
        }
    if drift > recheck_threshold:
        return {
            "window": window,
            "trigger": "allocation_drift",
            "status": "needs_recheck",
            "reason": f"Simulated drift {drift:.4f} exceeds recheck threshold {recheck_threshold:.4f}.",
        }
    return {
        "window": window,
        "trigger": "allocation_drift",
        "status": "paper_monitor_ok",
        "reason": f"Simulated drift {drift:.4f} within recheck threshold {recheck_threshold:.4f}.",
    }


def _check_cash_reserve(
    *,
    window: int,
    allocations: list[dict[str, Any]],
    min_cash_weight: float,
) -> dict[str, Any]:
    """Check whether the cash reserve weight meets the minimum."""
    cash_weight = sum(
        _clean_weight(item.get("paper_weight"))
        for item in allocations
        if item.get("strategy") == "cash"
    )
    if cash_weight + 0.000001 < min_cash_weight:
        return {
            "window": window,
            "trigger": "cash_reserve_breach",
            "status": "rejected",
            "reason": f"Cash weight {cash_weight:.4f} below minimum {min_cash_weight:.4f}.",
        }
    return {
        "window": window,
        "trigger": "cash_reserve_breach",
        "status": "paper_monitor_ok",
        "reason": f"Cash weight {cash_weight:.4f} meets minimum {min_cash_weight:.4f}.",
    }


def _check_drawdown_breach(
    *,
    window: int,
    window_returns: list[float],
    allocations: list[dict[str, Any]],
    max_stressed_drawdown: float,
) -> dict[str, Any]:
    """Check whether simulated portfolio drawdown breaches the paper guardrail."""
    contributions = [
        {
            "strategy": item.get("strategy", "unknown"),
            "weight": _clean_weight(item.get("paper_weight")),
            "beta": _stress_beta(str(item.get("strategy", ""))),
        }
        for item in allocations
    ]
    portfolio_returns = []
    for r in window_returns:
        pr = 0.0
        for c in contributions:
            if c["strategy"] == "cash":
                continue
            pr += c["weight"] * c["beta"] * r
        portfolio_returns.append(pr)
    _, drawdown = _return_and_drawdown(portfolio_returns)
    if drawdown > max_stressed_drawdown:
        return {
            "window": window,
            "trigger": "drawdown_breach",
            "status": "rejected",
            "reason": f"Simulated drawdown {drawdown:.4f} exceeds paper guardrail {max_stressed_drawdown:.4f}.",
        }
    if drawdown > max_stressed_drawdown * 0.80:
        return {
            "window": window,
            "trigger": "drawdown_breach",
            "status": "paper_monitor_watchlist",
            "reason": f"Simulated drawdown {drawdown:.4f} near paper guardrail {max_stressed_drawdown:.4f}.",
        }
    return {
        "window": window,
        "trigger": "drawdown_breach",
        "status": "paper_monitor_ok",
        "reason": f"Simulated drawdown {drawdown:.4f} within paper guardrail {max_stressed_drawdown:.4f}.",
    }


def _check_stress_watchlist(
    *,
    window: int,
    stress_status: str,
) -> dict[str, Any]:
    """Check whether the stress status requires watchlist or recheck."""
    if stress_status == "paper_stress_watchlist":
        return {
            "window": window,
            "trigger": "stress_watchlist",
            "status": "paper_monitor_watchlist",
            "reason": "Stress report status is 'paper_stress_watchlist'; monitoring inherits watchlist.",
        }
    if stress_status == "needs_more_testing":
        return {
            "window": window,
            "trigger": "stress_watchlist",
            "status": "needs_recheck",
            "reason": "Stress report status is 'needs_more_testing'; monitoring requires recheck.",
        }
    return {
        "window": window,
        "trigger": "stress_watchlist",
        "status": "paper_monitor_ok",
        "reason": f"Stress report status is '{stress_status}'; no watchlist concern.",
    }


def _overall_monitoring_status(events: list[dict[str, Any]]) -> str:
    """Determine the overall monitoring status from all events."""
    statuses = {event["status"] for event in events}
    if "rejected" in statuses:
        return "rejected"
    if "needs_recheck" in statuses:
        return "needs_recheck"
    if "paper_monitor_watchlist" in statuses:
        return "paper_monitor_watchlist"
    return "paper_monitor_ok"
