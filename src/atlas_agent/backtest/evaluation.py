from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.engine import BacktestEngine
from atlas_agent.backtest.models import BacktestConfig, BacktestResult
from atlas_agent.backtest.registry import list_strategies


ARTIFACT_TYPE = "paper_strategy_evaluation"
SCHEMA_VERSION = 1
MIN_SAMPLE_ROWS = 10
PAPER_CANDIDATE_MAX_DRAWDOWN_PCT = 20.0
PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT = 0.0
ALLOWED_PAPER_DECISIONS = ("paper_candidate", "needs_more_testing", "rejected")

_DECISION_RANK = {
    "paper_candidate": 0,
    "needs_more_testing": 1,
    "rejected": 2,
}


def parse_strategy_list(raw: str | None) -> list[str]:
    if raw is None:
        return [item.strategy_id for item in list_strategies()]
    items: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        strategy_id = item.strip()
        if not strategy_id:
            continue
        if strategy_id not in seen:
            items.append(strategy_id)
            seen.add(strategy_id)
    if not items:
        raise ValueError("At least one strategy is required.")
    return items


def build_paper_strategy_evaluation(
    *,
    data_path: str | Path,
    symbol: str,
    strategies: Iterable[str] | None = None,
    initial_equity: float = 10000.0,
    slippage_bps: float = 0.0,
    commission_bps: float = 0.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Evaluate strategies through the deterministic paper backtest engine."""
    data_source = str(data_path)
    strategy_ids = list(strategies) if strategies is not None else parse_strategy_list(None)
    bars = load_market_data(data_source, symbol, start_date=start_date, end_date=end_date)
    sample = {
        "row_count": len(bars),
        "minimum_rows_for_candidate": MIN_SAMPLE_ROWS,
        "start": bars[0].timestamp.isoformat() if bars else None,
        "end": bars[-1].timestamp.isoformat() if bars else None,
    }

    entries: list[dict[str, Any]] = []
    for strategy_id in strategy_ids:
        entries.append(
            _evaluate_one_strategy(
                strategy_id=strategy_id,
                data_source=data_source,
                symbol=symbol,
                sample_row_count=len(bars),
                initial_equity=initial_equity,
                slippage_bps=slippage_bps,
                commission_bps=commission_bps,
                start_date=start_date,
                end_date=end_date,
            )
        )

    ranking = _rank_entries(entries)
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
        "data_source": data_source,
        "sample": sample,
        "gate_thresholds": {
            "minimum_rows_for_candidate": MIN_SAMPLE_ROWS,
            "paper_candidate_max_drawdown_pct": PAPER_CANDIDATE_MAX_DRAWDOWN_PCT,
            "paper_candidate_min_total_return_pct": PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT,
            "trade_activity_required_for_candidate": True,
        },
        "strategies": entries,
        "ranking": ranking,
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
        },
    }


def write_strategy_evaluation_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "strategy-evaluation.json"
    markdown_path = destination / "strategy-evaluation.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_strategy_evaluation_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_strategy_evaluation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Strategy Evaluation",
        "",
        (
            "**Status:** v0.6.13 planning line; paper-only; sample-data only; "
            "offline/no-provider/no-broker; not financial advice; not live "
            "readiness; no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Data source:** `{report['data_source']}`",
        f"**Rows:** {report.get('sample', {}).get('row_count', 0)}",
        "",
        (
            "This ranking is for paper follow-up only. It does not promote any "
            "strategy to live trading, autonomous live trading, or production use."
        ),
        "",
        "## Strategy Matrix",
        "",
        "| Strategy | Status | Return % | Max Drawdown % | Win Rate | Trades | Paper Gate |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["strategies"]:
        metrics = item.get("metrics", {})
        win_rate = metrics.get("win_rate")
        lines.append(
            "| {name} | {status} | {ret} | {dd} | {win} | {trades} | {gate} |".format(
                name=item["name"],
                status=item["status"],
                ret=_format_pct(metrics.get("total_return_pct")),
                dd=_format_pct(metrics.get("max_drawdown_pct")),
                win=_format_ratio(win_rate),
                trades=metrics.get("trade_count", "n/a"),
                gate=item["paper_gate"]["decision"],
            )
        )

    lines.extend(["", "## Ranking", ""])
    for ranked in report["ranking"]:
        lines.append(f"{ranked['rank']}. `{ranked['strategy']}` - {ranked['reason']}")

    lines.extend(
        [
            "",
            "## Gate Decisions",
            "",
            "- `paper_candidate`: eligible for more paper-only follow-up.",
            "- `needs_more_testing`: deterministic run completed, but the sample or metrics are not enough for candidate status.",
            "- `rejected`: the run failed or hit a hard paper-evaluation blocker.",
            "",
            "No gate decision is approval for live trading.",
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


def _evaluate_one_strategy(
    *,
    strategy_id: str,
    data_source: str,
    symbol: str,
    sample_row_count: int,
    initial_equity: float,
    slippage_bps: float,
    commission_bps: float,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    config = BacktestConfig(
        run_id=f"paper-eval-{_slug(strategy_id)}",
        symbol=symbol,
        data_path=data_source,
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        start_date=start_date,
        end_date=end_date,
        strategy_mode=strategy_id,
        benchmark_mode="buy_and_hold",
        risk_enabled=True,
        kill_switch_state=False,
    )
    try:
        result = BacktestEngine(config).run()
    except Exception as exc:
        return _failed_entry(strategy_id=strategy_id, error=str(exc))

    metrics = _metrics_payload(result)
    safety_blockers = _safety_blockers(result)
    paper_gate = _paper_gate(
        result=result,
        metrics=metrics,
        sample_row_count=sample_row_count,
        safety_blockers=safety_blockers,
    )
    metadata = result.strategy_metadata or {}
    return {
        "name": strategy_id,
        "display_name": metadata.get("name", strategy_id),
        "status": "evaluated",
        "metrics": metrics,
        "paper_gate": paper_gate,
        "live_ready": False,
        "risk_manager_enabled": result.config.risk_enabled,
        "kill_switch_state": result.config.kill_switch_state,
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "safety_blocker_count": len(safety_blockers),
        "safety_blockers": safety_blockers,
    }


def _failed_entry(*, strategy_id: str, error: str) -> dict[str, Any]:
    return {
        "name": strategy_id,
        "display_name": strategy_id,
        "status": "failed",
        "metrics": {
            "total_return": None,
            "max_drawdown": None,
            "win_rate": None,
            "total_return_pct": None,
            "max_drawdown_pct": None,
            "trade_count": 0,
            "sharpe_ratio": None,
        },
        "paper_gate": {
            "decision": "rejected",
            "reason": f"Backtest failed in paper evaluation: {error}",
        },
        "live_ready": False,
        "risk_manager_enabled": True,
        "kill_switch_state": False,
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "safety_blocker_count": 0,
        "safety_blockers": [],
        "error": error,
    }


def _metrics_payload(result: BacktestResult) -> dict[str, Any]:
    metrics = result.metrics
    total_return_pct = _clean_number(metrics.total_return_pct)
    max_drawdown_pct = _clean_number(metrics.max_drawdown_pct)
    return {
        "total_return": _ratio_from_pct(total_return_pct),
        "max_drawdown": _ratio_from_pct(max_drawdown_pct),
        "win_rate": _clean_number(metrics.win_rate),
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "trade_count": int(metrics.trade_count),
        "sharpe_ratio": _clean_number(metrics.sharpe_ratio),
        "annualized_return_pct": _clean_number(metrics.annualized_return_pct),
        "best_trade_pct": _clean_number(metrics.best_trade_pct),
        "worst_trade_pct": _clean_number(metrics.worst_trade_pct),
        "average_trade_pct": _clean_number(metrics.average_trade_pct),
        "exposure_time_pct": _clean_number(metrics.exposure_time_pct),
        "buy_and_hold_return_pct": _clean_number(metrics.buy_and_hold_return_pct),
        "final_equity": _clean_number(metrics.final_equity),
        "initial_equity": _clean_number(metrics.initial_equity),
    }


def _safety_blockers(result: BacktestResult) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for item in (result.diagnostics or {}).get("blocked_orders", []):
        violations = []
        for violation in item.get("violations", []):
            violations.append(
                {
                    "rule": violation.get("rule"),
                    "message": violation.get("message"),
                    "limit_value": _clean_number(violation.get("limit_value")),
                    "actual_value": _clean_number(violation.get("actual_value")),
                }
            )
        blockers.append(
            {
                "order_id": item.get("order_id"),
                "reason": item.get("reason"),
                "violations": violations,
            }
        )
    return blockers


def _paper_gate(
    *,
    result: BacktestResult,
    metrics: dict[str, Any],
    sample_row_count: int,
    safety_blockers: list[dict[str, Any]],
) -> dict[str, str]:
    if result.status != "completed":
        return {
            "decision": "rejected",
            "reason": "Backtest did not complete; rejected for paper evaluation.",
        }
    if safety_blockers:
        return {
            "decision": "rejected",
            "reason": (
                "RiskManager blocked one or more paper orders; rejected for "
                "paper evaluation. Inspect safety_blockers for audit detail."
            ),
        }
    if not _required_metrics_are_finite(metrics):
        return {
            "decision": "rejected",
            "reason": "Required metrics are missing or non-finite.",
        }
    if sample_row_count < MIN_SAMPLE_ROWS:
        return {
            "decision": "needs_more_testing",
            "reason": (
                f"Sample has {sample_row_count} rows; at least {MIN_SAMPLE_ROWS} "
                "rows are required for paper candidate status."
            ),
        }
    if metrics["max_drawdown_pct"] > PAPER_CANDIDATE_MAX_DRAWDOWN_PCT:
        return {
            "decision": "rejected",
            "reason": (
                "Max drawdown exceeded the documented demo paper threshold; "
                "rejected for paper evaluation."
            ),
        }
    if int(metrics.get("trade_count") or 0) <= 0:
        return {
            "decision": "needs_more_testing",
            "reason": (
                "Backtest completed with finite metrics but generated no fills "
                "on the bundled sample; more paper data or parameter testing is required."
            ),
        }
    if metrics["total_return_pct"] < PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT:
        return {
            "decision": "needs_more_testing",
            "reason": (
                "Backtest completed, but total return is below the documented "
                "demo paper threshold; more paper testing is required."
            ),
        }
    return {
        "decision": "paper_candidate",
        "reason": (
            "Backtest completed with finite metrics, no safety blockers, enough "
            "sample rows, trade activity, and drawdown within the demo threshold; "
            "paper-only follow-up only."
        ),
    }


def _rank_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(entries, key=_rank_key)
    output: list[dict[str, Any]] = []
    for index, item in enumerate(ranked, start=1):
        metrics = item.get("metrics", {})
        decision = item.get("paper_gate", {}).get("decision", "rejected")
        output.append(
            {
                "rank": index,
                "strategy": item["name"],
                "decision": decision,
                "reason": (
                    f"decision={decision}; total_return={_format_pct(metrics.get('total_return_pct'))}; "
                    f"max_drawdown={_format_pct(metrics.get('max_drawdown_pct'))}; "
                    "ties break deterministically by strategy id."
                ),
            }
        )
    return output


def _rank_key(item: dict[str, Any]) -> tuple[Any, ...]:
    metrics = item.get("metrics", {})
    decision = item.get("paper_gate", {}).get("decision", "rejected")
    total_return = _sort_number(metrics.get("total_return_pct"), default=-math.inf)
    max_drawdown = _sort_number(metrics.get("max_drawdown_pct"), default=math.inf)
    win_rate = _sort_number(metrics.get("win_rate"), default=-math.inf)
    trade_count = int(metrics.get("trade_count") or 0)
    return (
        _DECISION_RANK.get(decision, _DECISION_RANK["rejected"]),
        max_drawdown,
        -total_return,
        -win_rate,
        -trade_count,
        item["name"],
    )


def _required_metrics_are_finite(metrics: dict[str, Any]) -> bool:
    for key in ("total_return_pct", "max_drawdown_pct", "win_rate"):
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return False
    return True


def _clean_number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    as_float = float(value)
    if not math.isfinite(as_float):
        return None
    rounded = round(as_float, 10)
    if isinstance(value, int):
        return int(value)
    return rounded


def _ratio_from_pct(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / 100.0, 10)


def _sort_number(value: Any, *, default: float) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return default
    return float(value)


def _format_pct(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{float(value):.4f}%"


def _format_ratio(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{float(value):.4f}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "strategy"
