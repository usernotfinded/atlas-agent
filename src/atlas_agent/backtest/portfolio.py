from __future__ import annotations

import csv
import hashlib
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


def build_paper_portfolio_recheck(
    data_path: str,
    symbol: str,
    strategies: list[str] | None = None,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    max_stressed_drawdown: float = 0.25,
    max_single_scenario_loss: float = 0.20,
    monitor_window: int = 20,
    recheck_threshold: float = 0.05,
) -> dict[str, Any]:
    """Generate a deterministic paper-only portfolio recheck ledger.

    No provider network, broker calls, notifications, or live execution path used.
    """
    # 1. Generate prior artifacts deterministically
    proposal = build_paper_portfolio_proposal(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
    )

    stress = build_paper_portfolio_stress(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
    )

    monitoring = build_paper_portfolio_monitoring(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        monitor_window=monitor_window,
        recheck_threshold=recheck_threshold,
    )

    review_items = []

    # Check Proposal
    if proposal.get("overall_proposal_status") in ("needs_more_testing", "rejected"):
        review_items.append({
            "id": "review-proposal-001",
            "source": "proposal",
            "trigger": "insufficient_evidence",
            "status": "paper_recheck_required",
            "paper_action": "paper_collect_more_evidence",
            "severity": "medium",
            "reason": "Proposal lacks stable evidence.",
        })

    # Check Stress
    if stress.get("overall_stress_status") in ("watchlist", "needs_more_testing", "rejected"):
        review_items.append({
            "id": "review-stress-001",
            "source": "stress",
            "trigger": "stress_watchlist",
            "status": "paper_review_watchlist",
            "paper_action": "paper_watchlist_review",
            "severity": "high",
            "reason": "Stress boundaries breached in synthetic simulation.",
        })

    # Check Monitoring
    for i, event in enumerate(monitoring.get("monitoring_events", [])):
        if event.get("event_type") == "allocation_drift":
            review_items.append({
                "id": f"review-monitor-alloc-{i+1:03d}",
                "source": "monitoring",
                "trigger": "allocation_drift",
                "status": "paper_recheck_required",
                "paper_action": "paper_recheck",
                "severity": "medium",
                "reason": "Drift exceeded threshold in offline simulation.",
            })
        elif event.get("event_type") == "cash_reserve_breach":
            review_items.append({
                "id": f"review-monitor-cash-{i+1:03d}",
                "source": "monitoring",
                "trigger": "cash_reserve_breach",
                "status": "paper_review_watchlist",
                "paper_action": "paper_increase_cash_review",
                "severity": "high",
                "reason": "Cash reserves critically low in offline simulation.",
            })
        elif event.get("event_type") == "drawdown_breach":
            review_items.append({
                "id": f"review-monitor-dd-{i+1:03d}",
                "source": "monitoring",
                "trigger": "drawdown_breach",
                "status": "paper_rejected",
                "paper_action": "paper_reject_portfolio",
                "severity": "critical",
                "reason": "Hard drawdown stop exceeded in offline simulation.",
            })

    if monitoring.get("overall_monitoring_status") == "paper_monitor_watchlist":
        review_items.append({
            "id": "review-monitor-watchlist-001",
            "source": "monitoring",
            "trigger": "monitoring_watchlist",
            "status": "paper_review_watchlist",
            "paper_action": "paper_reduce_weight_review",
            "severity": "medium",
            "reason": "General watchlist trigger detected.",
        })

    if not review_items:
        review_items.append({
            "id": "review-clear-001",
            "source": "system",
            "trigger": "clean_run",
            "status": "paper_review_clear",
            "paper_action": "no_action_paper_only",
            "severity": "info",
            "reason": "No review triggers found in paper simulation.",
        })

    review_queue = []
    for i, item in enumerate(review_items):
        review_queue.append({
            "rank": i + 1,
            "review_item_id": item["id"],
            "paper_action": item["paper_action"],
            "human_review_required": item["status"] != "paper_review_clear",
        })

    overall_status = "paper_review_clear"
    for item in review_items:
        if item["status"] == "paper_rejected":
            overall_status = "paper_rejected"
            break
        elif item["status"] in ("paper_recheck_required", "paper_review_watchlist"):
            if overall_status != "paper_rejected":
                overall_status = item["status"]

    return {
        "artifact_type": "paper_portfolio_recheck_ledger",
        "schema_version": 1,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
        "symbol": symbol,
        "data_source": data_path,
        "proposal_source": "generated",
        "stress_source": "generated",
        "monitoring_source": "generated",
        "overall_review_status": overall_status,
        "review_items": review_items,
        "review_queue": review_queue,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_notifications_sent": True,
            "no_orders_generated": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
        },
    }


def write_portfolio_recheck_reports(
    report: dict[str, Any],
    output_dir: str,
) -> tuple[str, str]:
    """Write paper portfolio recheck ledger and queue reports to disk."""
    import os
    import json

    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "paper-portfolio-recheck-ledger.json")
    md_path = os.path.join(output_dir, "paper-portfolio-review-queue.md")

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)

    lines = [
        "# Paper Portfolio Review Queue",
        "",
        "> **Note:** This is a deterministic paper-only review queue simulation.",
        "> It is NOT financial advice, does NOT imply live-readiness, and NO orders or real notifications are generated.",
        "> It does NOT guarantee profit and is purely for offline sandbox verification.",
        "",
        f"**Symbol**: {report['symbol']}",
        f"**Data Source**: {report['data_source']}",
        f"**Overall Review Status**: `{report['overall_review_status']}`",
        "",
        "## Safety Assertions",
        "- `live_readiness`: False",
        "- `broker_required`: False",
        "- `provider_required`: False",
        "- `no_notifications_sent`: True",
        "- `no_orders_generated`: True",
        "",
        "## Human Review Queue",
    ]

    for item in report["review_queue"]:
        lines.append(f"### Rank {item['rank']} - {item['review_item_id']}")
        lines.append(f"- **Action**: `{item['paper_action']}`")
        lines.append(f"- **Human Review Required**: {item['human_review_required']}")
        lines.append("")

    lines.append("## Detailed Ledger Items")
    for item in report["review_items"]:
        lines.append(f"### {item['id']}")
        lines.append(f"- **Source**: {item['source']}")
        lines.append(f"- **Trigger**: `{item['trigger']}`")
        lines.append(f"- **Status**: `{item['status']}`")
        lines.append(f"- **Recommended Paper Action**: `{item['paper_action']}`")
        lines.append(f"- **Severity**: {item['severity']}")
        lines.append(f"- **Reason**: {item['reason']}")
        lines.append("")

    lines.append("---")
    lines.append("Generated offline safely. No live data or APIs used.")

    with open(md_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return json_path, md_path


def build_paper_portfolio_dossier(
    data_path: str,
    symbol: str,
    strategies: list[str] | None = None,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    max_stressed_drawdown: float = 0.25,
    max_single_scenario_loss: float = 0.20,
    monitor_window: int = 20,
    recheck_threshold: float = 0.05,
) -> dict[str, Any]:
    """Generate a deterministic paper-only portfolio reviewer dossier."""
    import hashlib
    import json

    proposal = build_paper_portfolio_proposal(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
    )
    stress = build_paper_portfolio_stress(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
    )
    monitoring = build_paper_portfolio_monitoring(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        monitor_window=monitor_window,
        recheck_threshold=recheck_threshold,
    )
    recheck = build_paper_portfolio_recheck(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        monitor_window=monitor_window,
        recheck_threshold=recheck_threshold,
    )

    def _hash(obj):
        return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    artifacts = [
        {
            "name": "paper-portfolio-proposal.json",
            "artifact_type": "paper_portfolio_proposal",
            "digest": _hash(proposal),
        },
        {
            "name": "paper-portfolio-stress.json",
            "artifact_type": "paper_portfolio_stress",
            "digest": _hash(stress),
        },
        {
            "name": "paper-portfolio-monitoring.json",
            "artifact_type": "paper_portfolio_monitoring",
            "digest": _hash(monitoring),
        },
        {
            "name": "paper-portfolio-recheck-ledger.json",
            "artifact_type": "paper_portfolio_recheck_ledger",
            "digest": _hash(recheck),
        },
    ]

    recheck_status = recheck.get("overall_review_status", "paper_recheck_ok")
    if recheck_status == "paper_recheck_required":
        dossier_status = "paper_dossier_recheck_required"
    elif recheck_status == "paper_review_watchlist":
        dossier_status = "paper_dossier_watchlist"
    elif recheck_status == "paper_recheck_rejected":
        dossier_status = "paper_dossier_rejected"
    else:
        dossier_status = "paper_dossier_complete"

    human_review_checklist = [
        {"item": "Review paper-only allocation guardrails", "required": True},
        {"item": "Review stress constraints", "required": True},
        {"item": "Review monitoring/recheck triggers", "required": True},
        {"item": "Verify artifact consistency", "required": True},
        {"item": "Verify safety boundaries", "required": True},
    ]

    return {
        "artifact_type": "paper_portfolio_dossier",
        "schema_version": 1,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
        "symbol": symbol,
        "data_source": data_path,
        "overall_dossier_status": dossier_status,
        "artifacts": artifacts,
        "summaries": {
            "proposal": {"status": proposal.get("overall_proposal_status")},
            "stress": {"status": stress.get("overall_stress_status")},
            "monitoring": {"status": monitoring.get("overall_monitoring_status")},
            "recheck": {"status": recheck_status, "queue_size": len(recheck.get("review_queue", []))},
        },
        "human_review_checklist": human_review_checklist,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_notifications_sent": True,
            "no_orders_generated": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
        },
    }

def write_portfolio_dossier_reports(
    report: dict[str, Any],
    output_dir: str,
) -> tuple[str, str, str]:
    """Write paper portfolio dossier, markdown, and evidence manifest to disk."""
    import os
    import json
    import hashlib

    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "paper-portfolio-dossier.json")
    md_path = os.path.join(output_dir, "paper-portfolio-dossier.md")
    manifest_path = os.path.join(output_dir, "paper-portfolio-evidence-manifest.json")

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)

    manifest = {
        "manifest_type": "paper_portfolio_evidence_manifest",
        "symbol": report.get("symbol"),
        "dossier_digest": hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "artifacts": report.get("artifacts", []),
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True, default=str)

    lines = [
        "# Paper Portfolio Reviewer Dossier",
        "",
        "**PAPER ONLY. NOT FINANCIAL ADVICE. NO LIVE READINESS. NO PROFIT GUARANTEE.**",
        "**NO PROVIDERS CALLED. NO BROKERS CALLED. NO REAL NOTIFICATIONS SENT. NO ORDERS GENERATED.**",
        "",
        f"- **Symbol:** {report.get('symbol')}",
        f"- **Overall Dossier Status:** `{report.get('overall_dossier_status')}`",
        "",
        "## Human Review Checklist",
        "",
    ]
    for item in report.get("human_review_checklist", []):
        lines.append(f"- [ ] {item['item']} (Required: {item['required']})")

    lines.extend([
        "",
        "## Summaries",
        "",
        f"- **Proposal:** `{report['summaries']['proposal']['status']}`",
        f"- **Stress:** `{report['summaries']['stress']['status']}`",
        f"- **Monitoring:** `{report['summaries']['monitoring']['status']}`",
        f"- **Recheck:** `{report['summaries']['recheck']['status']}` (Queue size: {report['summaries']['recheck']['queue_size']})",
        "",
        "## Generated Artifacts",
        "",
    ])
    for art in report.get("artifacts", []):
        lines.append(f"- `{art['name']}`: {art['digest'][:8]}")

    with open(md_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return json_path, md_path, manifest_path


def build_paper_portfolio_replay(
    data_path: str,
    symbol: str,
    strategies: list[str] | None = None,
    repeat: int = 2,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    max_stressed_drawdown: float = 0.25,
    max_single_scenario_loss: float = 0.20,
    monitor_window: int = 20,
    recheck_threshold: float = 0.05,
) -> dict[str, Any]:
    """Generate a deterministic paper-only portfolio evidence replay and regression gate."""
    import hashlib
    import json

    runs = []
    comparisons = []
    stable_artifacts = {}
    overall_status = "paper_replay_pass"

    # Capture the last dossier structure to check schema version
    last_dossier = {}

    for run_index in range(1, repeat + 1):
        dossier = build_paper_portfolio_dossier(
            data_path=data_path,
            symbol=symbol,
            strategies=strategies,
            max_strategy_weight=max_strategy_weight,
            min_cash_weight=min_cash_weight,
            max_stressed_drawdown=max_stressed_drawdown,
            max_single_scenario_loss=max_single_scenario_loss,
            monitor_window=monitor_window,
            recheck_threshold=recheck_threshold,
        )
        last_dossier = dossier

        run_artifacts = []
        for art in dossier.get("artifacts", []):
            run_artifacts.append({
                "name": art["name"],
                "artifact_type": art["artifact_type"],
                "stable_digest": art["digest"]
            })

        def _stable_hash(obj):
            return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        dossier_hash = _stable_hash(dossier)
        run_artifacts.append({
            "name": "paper-portfolio-dossier.json",
            "artifact_type": "paper_portfolio_dossier",
            "stable_digest": dossier_hash
        })

        runs.append({
            "run_index": run_index,
            "artifacts": run_artifacts
        })

        if run_index == 1:
            for art in run_artifacts:
                stable_artifacts[art["name"]] = art["stable_digest"]
        else:
            for art in run_artifacts:
                name = art["name"]
                expected = stable_artifacts.get(name)
                actual = art["stable_digest"]
                if expected != actual:
                    overall_status = "paper_replay_drift_detected"
                    comparisons.append({
                        "artifact_name": name,
                        "status": "mismatch",
                        "expected_digest": expected,
                        "stable_digest": actual,
                    })
                else:
                    comparisons.append({
                        "artifact_name": name,
                        "status": "match",
                        "stable_digest": actual,
                    })

    if last_dossier.get("schema_version") != 1:
        overall_status = "paper_replay_schema_mismatch"
    elif overall_status == "paper_replay_pass" and last_dossier.get("overall_dossier_status") in ("paper_dossier_recheck_required", "paper_dossier_watchlist"):
        overall_status = "needs_recheck"
    elif overall_status == "paper_replay_pass" and last_dossier.get("overall_dossier_status") == "paper_dossier_rejected":
        overall_status = "rejected"

    return {
        "artifact_type": "paper_portfolio_replay",
        "schema_version": 1,
        "mode": "paper",
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_readiness": False,
        "not_financial_advice": True,
        "symbol": symbol,
        "data_source": data_path,
        "repeat": repeat,
        "overall_replay_status": overall_status,
        "runs": runs,
        "comparisons": comparisons,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_notifications_sent": True,
            "no_orders_generated": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
        },
    }

def write_portfolio_replay_reports(
    report: dict[str, Any],
    output_dir: str,
) -> tuple[str, str, str]:
    """Write paper portfolio replay reports to disk."""
    import os
    import json
    import hashlib

    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "paper-portfolio-replay.json")
    md_path = os.path.join(output_dir, "paper-portfolio-replay.md")
    manifest_path = os.path.join(output_dir, "paper-portfolio-regression-manifest.json")

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)

    manifest = {
        "manifest_type": "paper_portfolio_regression_manifest",
        "symbol": report.get("symbol"),
        "replay_digest": hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "runs": report.get("runs", []),
        "comparisons": report.get("comparisons", []),
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True, default=str)

    lines = [
        "# Paper Portfolio Replay and Regression Gate",
        "",
        "**PAPER ONLY. NOT FINANCIAL ADVICE. NO LIVE READINESS. NO PROFIT GUARANTEE.**",
        "**NO PROVIDERS CALLED. NO BROKERS CALLED. NO REAL NOTIFICATIONS SENT. NO ORDERS GENERATED.**",
        "",
        f"- **Symbol:** {report.get('symbol')}",
        f"- **Overall Replay Status:** `{report.get('overall_replay_status')}`",
        f"- **Repeat Count:** {report.get('repeat')}",
        "",
        "## Comparisons",
        "",
    ]

    seen = set()
    for comp in report.get("comparisons", []):
        key = f"{comp['artifact_name']}-{comp['status']}"
        if key not in seen:
            lines.append(f"- `{comp['artifact_name']}`: `{comp['status']}` (Digest: {comp['stable_digest'][:8]})")
            seen.add(key)

    with open(md_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return json_path, md_path, manifest_path


REVIEW_PACK_ARTIFACT_TYPE = "paper_human_review_pack"
REVIEW_PACK_SCHEMA_VERSION = 1
REVIEW_PACK_RELEASE = "v0.6.15-planning"
REVIEW_PACK_SOURCE_RELEASE = "v0.6.14"
ALLOWED_REVIEW_PACK_STATUSES = {
    "paper_review_pack_open",
    "paper_review_pack_follow_up",
    "paper_review_pack_rejected",
}
ALLOWED_REVIEW_ITEM_STATUSES = {
    "needs_human_review",
    "needs_more_paper_testing",
    "rejected_from_review",
    "paper_only_follow_up",
}


def build_paper_portfolio_review_pack(
    *,
    data_path: str | Path,
    symbol: str,
    strategies: list[str] | None = None,
    proposal: dict[str, Any] | None = None,
    stress: dict[str, Any] | None = None,
    monitoring: dict[str, Any] | None = None,
    recheck: dict[str, Any] | None = None,
    dossier: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    max_strategy_weight: float = 0.40,
    min_cash_weight: float = 0.10,
    max_stressed_drawdown: float = 0.25,
    max_single_scenario_loss: float = 0.20,
    monitor_window: int = 20,
    recheck_threshold: float = 0.05,
) -> dict[str, Any]:
    """Generate a deterministic paper-only human review pack.

    The pack converts paper portfolio evidence into a non-executable review
    dossier. It does not generate orders, call providers or brokers, send
    notifications, or claim live readiness.
    """
    dossier_report = dossier or build_paper_portfolio_dossier(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        monitor_window=monitor_window,
        recheck_threshold=recheck_threshold,
    )
    replay_report = replay or build_paper_portfolio_replay(
        data_path=data_path,
        symbol=symbol,
        strategies=strategies,
        repeat=2,
        max_strategy_weight=max_strategy_weight,
        min_cash_weight=min_cash_weight,
        max_stressed_drawdown=max_stressed_drawdown,
        max_single_scenario_loss=max_single_scenario_loss,
        monitor_window=monitor_window,
        recheck_threshold=recheck_threshold,
    )

    review_items: list[dict[str, Any]] = []

    if replay_report.get("overall_replay_status") == "paper_replay_drift_detected":
        review_items.append({
            "id": "review-001",
            "type": "paper_review_item",
            "source": "paper_portfolio_replay",
            "status": "needs_human_review",
            "severity": "high",
            "reason": "Replay detected deterministic drift between runs; human review required before any follow-up.",
            "non_executable_action": "paper_only_follow_up",
        })

    if dossier_report.get("overall_dossier_status") == "paper_dossier_recheck_required":
        review_items.append({
            "id": "review-002",
            "type": "paper_review_item",
            "source": "paper_portfolio_dossier",
            "status": "needs_human_review",
            "severity": "high",
            "reason": "Dossier recheck flag raised; reviewer must inspect artifacts offline.",
            "non_executable_action": "paper_only_follow_up",
        })
    elif dossier_report.get("overall_dossier_status") == "paper_dossier_watchlist":
        review_items.append({
            "id": "review-003",
            "type": "paper_review_item",
            "source": "paper_portfolio_dossier",
            "status": "needs_more_paper_testing",
            "severity": "medium",
            "reason": "Dossier watchlist status indicates more paper testing is needed.",
            "non_executable_action": "paper_only_follow_up",
        })
    elif dossier_report.get("overall_dossier_status") == "paper_dossier_rejected":
        review_items.append({
            "id": "review-004",
            "type": "paper_review_item",
            "source": "paper_portfolio_dossier",
            "status": "rejected_from_review",
            "severity": "high",
            "reason": "Dossier rejected; this candidate is closed from review.",
            "non_executable_action": "paper_only_follow_up",
        })

    if not review_items:
        review_items.append({
            "id": "review-005",
            "type": "paper_review_item",
            "source": "paper_portfolio_review_pack",
            "status": "needs_human_review",
            "severity": "low",
            "reason": "No automated flags raised; human reviewer should still confirm paper-only scope and safety invariants.",
            "non_executable_action": "paper_only_follow_up",
        })

    if replay_report.get("overall_replay_status") in ("needs_recheck", "rejected"):
        review_pack_status = "paper_review_pack_follow_up"
    elif dossier_report.get("overall_dossier_status") in ("paper_dossier_recheck_required", "paper_dossier_watchlist"):
        review_pack_status = "paper_review_pack_follow_up"
    elif dossier_report.get("overall_dossier_status") == "paper_dossier_rejected":
        review_pack_status = "paper_review_pack_rejected"
    else:
        review_pack_status = "paper_review_pack_open"

    artifact_digests = []
    for art in dossier_report.get("artifacts", []):
        artifact_digests.append({
            "name": art.get("name"),
            "artifact_type": art.get("artifact_type"),
            "digest": art.get("digest"),
        })

    return {
        "artifact_type": REVIEW_PACK_ARTIFACT_TYPE,
        "schema_version": REVIEW_PACK_SCHEMA_VERSION,
        "release": REVIEW_PACK_RELEASE,
        "mode": "paper",
        "source_release": REVIEW_PACK_SOURCE_RELEASE,
        "non_executable": True,
        "paper_only": True,
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_submit_enabled": False,
        "orders_generated": False,
        "notifications_sent": False,
        "not_financial_advice": True,
        "not_live_ready": True,
        "symbol": symbol,
        "data_source": str(data_path),
        "overall_review_pack_status": review_pack_status,
        "review_items": review_items,
        "artifact_digests": artifact_digests,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_notifications_sent": True,
            "no_orders_generated": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
            "non_executable": True,
            "paper_only": True,
        },
    }


def write_portfolio_review_pack_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write paper human review pack JSON and Markdown reports."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "paper-human-review-pack.json"
    md_path = destination / "paper-human-review-pack.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_portfolio_review_pack_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_portfolio_review_pack_markdown(report: dict[str, Any]) -> str:
    """Render a non-executable paper-only human review pack Markdown report."""
    lines = [
        "# Paper Human Review Pack",
        "",
        "**PAPER-ONLY. NON-EXECUTABLE. NOT FINANCIAL ADVICE. NOT LIVE READY.**",
        "**NO BROKER SUBMISSION. NO PROVIDER CALLS. NO REAL NOTIFICATIONS. NO ORDERS GENERATED.**",
        "**NO ACCOUNT-SPECIFIC INSTRUCTIONS. NO PROFIT GUARANTEES. NO ABSOLUTE SAFETY CLAIMS. NO CLAIMS THAT RISK IS ELIMINATED.**",
        "**NO LIVE-READINESS CLAIM. NO AUTONOMOUS LIVE TRADING READINESS CLAIM.**",
        "**HUMAN REVIEW IS REQUIRED BEFORE ANY FUTURE LIVE-RELATED WORK.**",
        "",
        f"- **Release**: `{report.get('release')}`",
        f"- **Source Release**: `{report.get('source_release')}`",
        f"- **Symbol**: `{report.get('symbol')}`",
        f"- **Overall Review Pack Status**: `{report.get('overall_review_pack_status')}`",
        "",
        "## Safety Assertions",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| `non_executable` | `{report.get('non_executable')}` |",
        f"| `paper_only` | `{report.get('paper_only')}` |",
        f"| `provider_required` | `{report.get('provider_required')}` |",
        f"| `broker_required` | `{report.get('broker_required')}` |",
        f"| `network_required` | `{report.get('network_required')}` |",
        f"| `live_submit_enabled` | `{report.get('live_submit_enabled')}` |",
        f"| `orders_generated` | `{report.get('orders_generated')}` |",
        f"| `notifications_sent` | `{report.get('notifications_sent')}` |",
        f"| `not_financial_advice` | `{report.get('not_financial_advice')}` |",
        f"| `not_live_ready` | `{report.get('not_live_ready')}` |",
        "",
        "## Review Items",
        "",
    ]

    for item in report.get("review_items", []):
        lines.append(f"### {item.get('id')} ({item.get('source')})")
        lines.append(f"- **Type**: `{item.get('type')}`")
        lines.append(f"- **Status**: `{item.get('status')}`")
        lines.append(f"- **Severity**: `{item.get('severity')}`")
        lines.append(f"- **Reason**: {item.get('reason')}")
        lines.append(f"- **Non-Executable Action**: `{item.get('non_executable_action')}`")
        lines.append("")

    lines.extend([
        "## Source Artifact Digests",
        "",
    ])
    for art in report.get("artifact_digests", []):
        digest = art.get("digest", "")[:8] if art.get("digest") else "n/a"
        lines.append(f"- `{art.get('name')}` ({art.get('artifact_type')}): `{digest}`")

    lines.extend([
        "",
        "## What This Pack Is For",
        "",
        "This dossier helps a human reviewer understand what the paper system would like reviewed next. "
        "It is intentionally non-executable: it cannot be confused with an order, trade instruction, "
        "broker submission, provider request, or live-trading signal.",
        "",
        "## What This Pack Is NOT",
        "",
        "- It is NOT a live trading authorization.",
        "- It is NOT an executable order ticket or account-specific instruction.",
        "- It is NOT a claim that the portfolio, strategy, or system is ready for live trading.",
        "- It is NOT a guarantee of profit, outperformance, or risk-free operation.",
        "- It does NOT call brokers, providers, notification services, or any network API.",
        "",
        "---",
        "Generated offline from deterministic paper portfolio evidence. No live data or APIs used.",
    ])

    return "\n".join(lines) + "\n"


REVIEW_LEDGER_ARTIFACT_TYPE = "paper_human_review_ledger"
REVIEW_LEDGER_SCHEMA_VERSION = 1
REVIEW_LEDGER_RELEASE = "v0.6.15-planning"
REVIEW_LEDGER_SOURCE_RELEASE = "v0.6.14"
ALLOWED_REVIEW_LEDGER_STATUSES = {
    "paper_review_ledger_open",
    "paper_review_ledger_follow_up",
    "paper_review_ledger_rejected",
}
ALLOWED_DECISION_STATUSES = {
    "paper_follow_up_allowed",
    "needs_more_paper_evidence",
    "rejected_from_paper_follow_up",
    "manual_review_required",
    "blocked_by_missing_evidence",
}


def build_paper_portfolio_review_ledger(
    *,
    review_pack_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    build_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a non-executable paper-only human review ledger from a review pack.

    The ledger consumes a paper human review pack (either loaded from JSON path or
    built deterministically) and produces simulated decision entries plus a gate
    summary. It is strictly paper-only: no broker submission, no live approval, no
    real human approval, no executable orders, no network calls.
    """
    if review_pack_path is not None:
        pack_path = Path(review_pack_path)
        pack_text = pack_path.read_text(encoding="utf-8")
        pack = json.loads(pack_text)
        source_digest = hashlib.sha256(pack_text.encode("utf-8")).hexdigest()
    elif build_kwargs is not None:
        pack = build_paper_portfolio_review_pack(**build_kwargs)
        pack_text = json.dumps(pack, sort_keys=True, allow_nan=False)
        source_digest = hashlib.sha256(pack_text.encode("utf-8")).hexdigest()
    else:
        raise ValueError(
            "Either review_pack_path or build_kwargs must be provided."
        )

    if pack.get("artifact_type") != "paper_human_review_pack":
        raise ValueError("Source artifact must be a paper_human_review_pack.")
    if pack.get("schema_version") != 1:
        raise ValueError("Source artifact schema_version must be 1.")

    status_map = {
        "rejected_from_review": "rejected_from_paper_follow_up",
        "needs_more_paper_testing": "needs_more_paper_evidence",
        "needs_human_review": "manual_review_required",
        "paper_only_follow_up": "paper_follow_up_allowed",
    }

    decision_entries: list[dict[str, Any]] = []
    for item in pack.get("review_items", []):
        item_status = item.get("status")
        decision_status = status_map.get(item_status, "blocked_by_missing_evidence")
        decision_entries.append(
            {
                "id": f"{item.get('id')}-decision",
                "type": "paper_decision_entry",
                "source_item_id": item.get("id"),
                "source": item.get("source"),
                "decision_status": decision_status,
                "paper_action": item.get("non_executable_action"),
                "severity": item.get("severity"),
                "reason": item.get("reason"),
                "non_executable": True,
                "paper_only": True,
                "live_submit_enabled": False,
                "broker_submission_allowed": False,
                "reviewed_by": "simulated_reviewer",
            }
        )

    pack_status = pack.get("overall_review_pack_status")
    if pack_status == "paper_review_pack_rejected":
        overall_status = "paper_review_ledger_rejected"
    elif pack_status == "paper_review_pack_follow_up":
        overall_status = "paper_review_ledger_follow_up"
    else:
        overall_status = "paper_review_ledger_open"

    source_safety = pack.get("safety", {})
    safety = dict(source_safety)
    safety["no_real_human_approval"] = True
    safety["non_executable"] = True
    safety["paper_only"] = True

    report: dict[str, Any] = {
        "artifact_type": REVIEW_LEDGER_ARTIFACT_TYPE,
        "schema_version": REVIEW_LEDGER_SCHEMA_VERSION,
        "release": REVIEW_LEDGER_RELEASE,
        "source_release": REVIEW_LEDGER_SOURCE_RELEASE,
        "mode": "paper",
        "non_executable": True,
        "paper_only": True,
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "live_submit_enabled": False,
        "orders_generated": False,
        "notifications_sent": False,
        "real_human_approval": False,
        "not_financial_advice": True,
        "not_live_ready": True,
        "source_artifact_type": "paper_human_review_pack",
        "source_artifact_digest": source_digest,
        "overall_review_ledger_status": overall_status,
        "decision_entries": decision_entries,
        "gate_summary": {
            "live_approval_granted": False,
            "broker_submission_allowed": False,
            "paper_follow_up_allowed": True,
        },
        "safety": safety,
    }

    if output_dir is not None:
        write_portfolio_review_ledger_reports(report, output_dir=output_dir)

    return report


def write_portfolio_review_ledger_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write paper human review ledger JSON and Markdown reports."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "paper-human-review-ledger.json"
    md_path = destination / "paper-human-review-ledger.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        render_portfolio_review_ledger_markdown(report), encoding="utf-8"
    )
    return json_path, md_path


def render_portfolio_review_ledger_markdown(report: dict[str, Any]) -> str:
    """Render a non-executable paper-only human review ledger Markdown report."""
    lines = [
        "# Paper Human Review Ledger",
        "",
        "**PAPER-ONLY. NON-EXECUTABLE. NOT FINANCIAL ADVICE. NOT LIVE READY.**",
        "**NO BROKER SUBMISSION. NO PROVIDER CALLS. NO REAL NOTIFICATIONS. NO ORDERS GENERATED.**",
        "**NO ACCOUNT-SPECIFIC INSTRUCTIONS. NO PROFIT GUARANTEES. NO ABSOLUTE SAFETY CLAIMS. NO CLAIMS THAT RISK IS ELIMINATED.**",
        "**NO LIVE-READINESS CLAIM. NO AUTONOMOUS LIVE TRADING READINESS CLAIM.**",
        "**NO REAL HUMAN APPROVAL. DECISIONS ARE SIMULATED FOR PAPER REVIEW ONLY.**",
        "",
        f"- **Release**: `{report.get('release')}`",
        f"- **Source Release**: `{report.get('source_release')}`",
        f"- **Overall Review Ledger Status**: `{report.get('overall_review_ledger_status')}`",
        f"- **Source Artifact Digest**: `{report.get('source_artifact_digest', '')[:8]}`",
        "",
        "## Safety Assertions",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| `non_executable` | `{report.get('non_executable')}` |",
        f"| `paper_only` | `{report.get('paper_only')}` |",
        f"| `provider_required` | `{report.get('provider_required')}` |",
        f"| `broker_required` | `{report.get('broker_required')}` |",
        f"| `network_required` | `{report.get('network_required')}` |",
        f"| `live_submit_enabled` | `{report.get('live_submit_enabled')}` |",
        f"| `orders_generated` | `{report.get('orders_generated')}` |",
        f"| `notifications_sent` | `{report.get('notifications_sent')}` |",
        f"| `real_human_approval` | `{report.get('real_human_approval')}` |",
        f"| `not_financial_advice` | `{report.get('not_financial_advice')}` |",
        f"| `not_live_ready` | `{report.get('not_live_ready')}` |",
        "",
        "## Gate Summary",
        "",
        "| Property | Value |",
        "|---|---|",
    ]

    gate_summary = report.get("gate_summary", {})
    lines.append(
        f"| `live_approval_granted` | `{gate_summary.get('live_approval_granted')}` |"
    )
    lines.append(
        f"| `broker_submission_allowed` | `{gate_summary.get('broker_submission_allowed')}` |"
    )
    lines.append(
        f"| paper follow up allowed | `{gate_summary.get('paper_follow_up_allowed')}` |"
    )

    lines.extend([
        "",
        "## Decision Entries",
        "",
    ])

    for entry in report.get("decision_entries", []):
        lines.append(f"### {entry.get('id')} ({entry.get('source')})")
        lines.append(f"- **Type**: `{entry.get('type')}`")
        lines.append(f"- **Decision Status**: `{entry.get('decision_status')}`")
        lines.append(f"- **Severity**: `{entry.get('severity')}`")
        lines.append(f"- **Reason**: {entry.get('reason')}")
        lines.append(f"- **Paper Action**: `{entry.get('paper_action')}`")
        lines.append(f"- **Non-Executable**: `{entry.get('non_executable')}`")
        lines.append(
            f"- **Broker Submission Allowed**: `{entry.get('broker_submission_allowed')}`"
        )
        lines.append(f"- **Reviewed By**: `{entry.get('reviewed_by')}`")
        lines.append("")

    lines.extend([
        "## What This Ledger Is NOT",
        "",
        "- It is NOT live approval.",
        "- It is NOT a real human decision.",
        "- It is NOT an executable order.",
        "- It is NOT a claim that the portfolio, strategy, or system is ready for live trading.",
        "- It is NOT a guarantee of profit, outperformance, or risk-free operation.",
        "- It does NOT call brokers, providers, notification services, or any network API.",
        "",
        "---",
        "Generated offline from deterministic paper evidence. No live data or APIs used.",
    ])

    return "\n".join(lines) + "\n"
