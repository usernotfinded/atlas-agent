# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/walk_forward.py
# PURPOSE: Walk-forward analysis: tune on a window, test on the NEXT one, roll
#          forward, repeat. The only backtest result here that was not fitted to the
#          data it is scored on — and therefore the only one worth much.
# DEPS:    backtest.engine, backtest.data, backtest.metrics
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.engine import BacktestEngine
from atlas_agent.backtest.evaluation import (
    MIN_SAMPLE_ROWS,
    PAPER_CANDIDATE_MAX_DRAWDOWN_PCT,
    PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT,
    _clean_number,
    _format_pct,
    _format_ratio,
    _metrics_payload,
    _required_metrics_are_finite,
    _safety_blockers,
    _slug,
    _sort_number,
    parse_strategy_list,
)
from atlas_agent.backtest.models import BacktestConfig, BacktestResult
from atlas_agent.backtest.sensitivity import _default_variants_for

ARTIFACT_TYPE = "paper_strategy_walk_forward"
SCHEMA_VERSION = 1
ALLOWED_WALK_FORWARD_STATUSES = (
    "robust_paper_follow_up",
    "window_sensitive_needs_more_testing",
    "needs_more_testing",
    "rejected",
)
_SUMMARY_RANK = {
    "robust_paper_follow_up": 0,
    "window_sensitive_needs_more_testing": 1,
    "needs_more_testing": 2,
    "rejected": 3,
}


def parse_data_list(raw: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        fixture = item.strip()
        if not fixture:
            continue
        if fixture not in seen:
            items.append(fixture)
            seen.add(fixture)
    if not items:
        raise ValueError("At least one window fixture is required.")
    return items


def build_paper_strategy_walk_forward(
    *,
    data_path: str | Path,
    symbol: str,
    window_size: int = 60,
    step_size: int = 30,
    strategies: Iterable[str] | None = None,
    initial_equity: float = 10000.0,
    slippage_bps: float = 0.0,
    commission_bps: float = 0.0,
) -> dict[str, Any]:
    strategy_ids = list(strategies) if strategies is not None else parse_strategy_list(None)

    # Generate windows
    bars = load_market_data(data_path, symbol)
    if len(bars) < window_size:
        raise ValueError(f"Not enough data to form one window of size {window_size}")

    windows = []
    start_idx = 0
    window_id = 1
    while start_idx + window_size <= len(bars):
        window_bars = bars[start_idx:start_idx + window_size]
        windows.append({
            "name": f"w{window_id:03d}",
            "data_source": str(data_path),
            "row_count": len(window_bars),
            "start_index": start_idx,
            "end_index": start_idx + window_size - 1,
            "start_date": window_bars[0].timestamp.isoformat(),
            "end_date": window_bars[-1].timestamp.isoformat(),
            "minimum_rows_for_candidate": MIN_SAMPLE_ROWS,
            "start": window_bars[0].timestamp.isoformat(),
            "end": window_bars[-1].timestamp.isoformat(),
        })
        start_idx += step_size
        window_id += 1

    if not windows:
        raise ValueError("At least one window is required.")

    entries: list[dict[str, Any]] = []
    ranking_inputs: list[dict[str, Any]] = []

    for strategy_id in strategy_ids:
        variants = _default_variants_for(strategy_id)
        window_results: list[dict[str, Any]] = []
        for variant_id, parameters in variants:
            for window in windows:
                result = _evaluate_window_variant(
                    strategy_id=strategy_id,
                    variant_id=variant_id,
                    parameters=parameters,
                    window=window,
                    symbol=symbol,
                    initial_equity=initial_equity,
                    slippage_bps=slippage_bps,
                    commission_bps=commission_bps,
                )
                window_results.append(result)
                ranking_inputs.append(
                    {
                        "strategy": strategy_id,
                        "variant_id": variant_id,
                        "window": window["name"],
                        "metrics": result["metrics"],
                        "paper_gate": result["paper_gate"],
                    }
                )

        summary = _summarize_strategy(
            window_results=window_results,
            window_count=len(windows),
            variant_count=len(variants),
        )
        entries.append(
            {
                "name": strategy_id,
                "variants_evaluated": len(variants),
                "window_results": window_results,
                "walk_forward_summary": summary,
            }
        )

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
        "windowing": {
            "window_size": window_size,
            "step_size": step_size,
            "windows_evaluated": len(windows)
        },
        "gate_thresholds": {
            "minimum_rows_for_candidate": MIN_SAMPLE_ROWS,
            "paper_candidate_max_drawdown_pct": PAPER_CANDIDATE_MAX_DRAWDOWN_PCT,
            "paper_candidate_min_total_return_pct": PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT,
            "trade_activity_required_for_candidate": True,
        },
        "strategies": entries,
        "ranking": _rank_strategies(entries, ranking_inputs),
        "safety": {
            "no_live_trading": True,
            "no_broker_calls": True,
            "no_provider_calls": True,
            "no_profit_claim": True,
            "no_live_readiness_claim": True,
        },
    }


def write_strategy_walk_forward_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "strategy-walk-forward.json"
    markdown_path = destination / "strategy-walk-forward.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_strategy_walk_forward_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_strategy_walk_forward_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Strategy Walk-Forward Report",
        "",
        (
            "**Status:** v0.6.13 planning line; paper-only; synthetic/sample-data only; "
            "offline/no-provider/no-broker; not financial advice; not live readiness; "
            "no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Windows:** {len(report.get('windows', []))}",
        "",
        (
            "This multi-window walk_forward report is for paper follow-up only. "
            "WalkForward across deterministic synthetic fixtures does not imply future "
            "performance and does not promote any strategy to live trading, autonomous "
            "live trading, or production use."
        ),
        "",
        "## Windows",
        "",
        "| Window | Data source | Rows |",
        "| --- | --- | ---: |",
    ]
    for window in report.get("windows", []):
        lines.append(
            f"| {window['name']} | `{window['data_source']}` | {window['row_count']} |"
        )

    lines.extend(
        [
            "",
            "## Strategy Matrix",
            "",
            "| Strategy | Window | Variant | Return % | Max Drawdown % | Win Rate | Trades | Paper Gate |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for strategy in report.get("strategies", []):
        for item in strategy.get("window_results", []):
            metrics = item.get("metrics", {})
            lines.append(
                "| {strategy} | {window} | {variant} | {ret} | {dd} | {win} | {trades} | {gate} |".format(
                    strategy=strategy["name"],
                    window=item["window"],
                    variant=item["variant_id"],
                    ret=_format_pct(metrics.get("total_return_pct")),
                    dd=_format_pct(metrics.get("max_drawdown_pct")),
                    win=_format_ratio(metrics.get("win_rate")),
                    trades=metrics.get("trade_count", "n/a"),
                    gate=item["paper_gate"]["decision"],
                )
            )

    lines.extend(["", "## WalkForward Summary", ""])
    for strategy in report.get("strategies", []):
        summary = strategy.get("walk_forward_summary", {})
        lines.append(
            "- `{name}`: `{status}` across {count} windows - {reason}".format(
                name=strategy["name"],
                status=summary.get("paper_follow_up_status", "rejected"),
                count=summary.get("windows_evaluated", 0),
                reason=summary.get("reason", ""),
            )
        )

    lines.extend(["", "## Ranking", ""])
    for ranked in report.get("ranking", []):
        lines.append(f"{ranked['rank']}. `{ranked['strategy']}` - {ranked['reason']}")

    lines.extend(
        [
            "",
            "## WalkForward Gate Decisions",
            "",
            "- `robust_paper_follow_up`: valid across windows for paper-only follow-up.",
            "- `window_sensitive_needs_more_testing`: mixed valid results suggest window sensitivity or possible overfit.",
            "- `needs_more_testing`: valid data exists, but evidence is insufficient for robust paper follow-up.",
            "- `rejected`: a run failed, metrics were invalid, or a safety blocker exists.",
            "",
            "No walk_forward decision is approval for live trading.",
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


def _evaluate_window_variant(
    *,
    strategy_id: str,
    variant_id: str,
    parameters: dict[str, Any],
    window: dict[str, Any],
    symbol: str,
    initial_equity: float,
    slippage_bps: float,
    commission_bps: float,
) -> dict[str, Any]:
    config = BacktestConfig(
        run_id=f"paper-robust-{_slug(window['name'])}-{_slug(variant_id)}",
        symbol=symbol,
        data_path=window["data_source"],
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        start_date=window["start_date"],
        end_date=window["end_date"],
        strategy_mode=strategy_id,
        strategy_parameters=parameters,
        benchmark_mode="buy_and_hold",
        risk_enabled=True,
        kill_switch_state=False,
    )
    try:
        result = BacktestEngine(config).run()
    except Exception as exc:
        return _failed_window_variant(
            window=window["name"],
            variant_id=variant_id,
            parameters=parameters,
            error=str(exc),
        )

    metrics = _metrics_payload(result)
    safety_blockers = _safety_blockers(result)
    return {
        "window": window["name"],
        "variant_id": variant_id,
        "parameters": parameters,
        "status": "evaluated",
        "metrics": metrics,
        "paper_gate": _paper_gate_walk_forward(
            result=result,
            metrics=metrics,
            sample_row_count=int(window["row_count"]),
            safety_blockers=safety_blockers,
        ),
        "live_ready": False,
        "risk_manager_enabled": result.config.risk_enabled,
        "kill_switch_state": result.config.kill_switch_state,
        "provider_required": False,
        "broker_required": False,
        "network_required": False,
        "safety_blocker_count": len(safety_blockers),
        "safety_blockers": safety_blockers,
    }


def _failed_window_variant(
    *,
    window: str,
    variant_id: str,
    parameters: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    return {
        "window": window,
        "variant_id": variant_id,
        "parameters": parameters,
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
            "reason": f"Backtest failed in paper walk_forward evaluation: {error}",
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


def _paper_gate_walk_forward(
    *,
    result: BacktestResult,
    metrics: dict[str, Any],
    sample_row_count: int,
    safety_blockers: list[dict[str, Any]],
) -> dict[str, str]:
    if result.status != "completed":
        return {
            "decision": "rejected",
            "reason": "Backtest did not complete; rejected for paper walk_forward evaluation.",
        }
    if safety_blockers:
        return {
            "decision": "rejected",
            "reason": "RiskManager blocked paper orders; rejected for paper walk_forward evaluation.",
        }
    if not _required_metrics_are_finite(metrics):
        return {
            "decision": "rejected",
            "reason": "Required metrics are missing or non-finite.",
        }
    if sample_row_count < MIN_SAMPLE_ROWS:
        return {
            "decision": "needs_more_testing",
            "reason": f"Window fixture has {sample_row_count} rows; at least {MIN_SAMPLE_ROWS} rows are required.",
        }
    if metrics["max_drawdown_pct"] > PAPER_CANDIDATE_MAX_DRAWDOWN_PCT:
        return {
            "decision": "rejected",
            "reason": "Max drawdown exceeded the documented demo paper threshold.",
        }
    if int(metrics.get("trade_count") or 0) <= 0:
        return {
            "decision": "needs_more_testing",
            "reason": "No fills generated on this synthetic window; more paper testing is required.",
        }
    if metrics["total_return_pct"] < PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT:
        return {
            "decision": "needs_more_testing",
            "reason": "Total return is below the documented demo paper threshold for this window.",
        }
    return {
        "decision": "paper_candidate",
        "reason": "Window run completed with finite metrics and no safety blockers; paper-only follow-up only.",
    }


def _summarize_strategy(
    *,
    window_results: list[dict[str, Any]],
    window_count: int,
    variant_count: int,
) -> dict[str, Any]:
    decisions = [item.get("paper_gate", {}).get("decision", "rejected") for item in window_results]
    valid_count = sum(1 for decision in decisions if decision != "rejected")
    candidate_count = sum(1 for decision in decisions if decision == "paper_candidate")
    rejected_count = sum(1 for decision in decisions if decision == "rejected")
    all_metrics_finite = all(_required_metrics_are_finite(item.get("metrics", {})) for item in window_results)
    all_completed = all(item.get("status") == "evaluated" for item in window_results)
    no_safety_blockers = all(int(item.get("safety_blocker_count") or 0) == 0 for item in window_results)
    complete_variant_count = 0
    for variant_id in sorted({item["variant_id"] for item in window_results}):
        variant_items = [item for item in window_results if item["variant_id"] == variant_id]
        if len(variant_items) == window_count and all(
            item.get("paper_gate", {}).get("decision") == "paper_candidate"
            for item in variant_items
        ):
            complete_variant_count += 1

    if (
        window_results
        and all_completed
        and all_metrics_finite
        and no_safety_blockers
        and complete_variant_count > 0
    ):
        status = "robust_paper_follow_up"
        reason = (
            "At least one variant completed every synthetic window with paper-candidate "
            "gates; paper-only follow-up only, not live readiness."
        )
    elif rejected_count and valid_count:
        status = "window_sensitive_needs_more_testing"
        reason = (
            "Results are mixed across windows or variants, which may indicate window "
            "sensitivity or one-fixture overfit; paper-only follow-up requires more testing."
        )
    elif valid_count:
        status = "needs_more_testing"
        reason = "Window runs were valid but insufficient for robust paper follow-up."
    else:
        status = "rejected"
        reason = "No valid window run passed the paper walk_forward gate."

    return {
        "windows_evaluated": window_count,
        "variants_evaluated": variant_count,
        "window_result_count": len(window_results),
        "paper_candidate_results": candidate_count,
        "non_rejected_results": valid_count,
        "rejected_results": rejected_count,
        "complete_paper_candidate_variants": complete_variant_count,
        "paper_follow_up_status": status,
        "reason": reason,
    }


def _rank_strategies(
    entries: list[dict[str, Any]],
    ranking_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    per_strategy: dict[str, list[dict[str, Any]]] = {}
    for item in ranking_inputs:
        per_strategy.setdefault(item["strategy"], []).append(item)

    ranked = sorted(entries, key=lambda item: _strategy_rank_key(item, per_strategy.get(item["name"], [])))
    output: list[dict[str, Any]] = []
    for index, item in enumerate(ranked, start=1):
        summary = item.get("walk_forward_summary", {})
        metrics = _aggregate_metrics(per_strategy.get(item["name"], []))
        output.append(
            {
                "rank": index,
                "strategy": item["name"],
                "paper_follow_up_status": summary.get("paper_follow_up_status", "rejected"),
                "reason": (
                    f"status={summary.get('paper_follow_up_status', 'rejected')}; "
                    f"candidate_results={summary.get('paper_candidate_results', 0)}; "
                    f"avg_total_return={_format_pct(metrics['avg_total_return_pct'])}; "
                    f"worst_max_drawdown={_format_pct(metrics['worst_max_drawdown_pct'])}; "
                    "ties break deterministically by strategy id."
                ),
            }
        )
    return output


def _strategy_rank_key(
    item: dict[str, Any],
    window_results: list[dict[str, Any]],
) -> tuple[Any, ...]:
    summary = item.get("walk_forward_summary", {})
    metrics = _aggregate_metrics(window_results)
    return (
        _SUMMARY_RANK.get(summary.get("paper_follow_up_status", "rejected"), _SUMMARY_RANK["rejected"]),
        -int(summary.get("complete_paper_candidate_variants") or 0),
        -int(summary.get("paper_candidate_results") or 0),
        _sort_number(metrics.get("worst_max_drawdown_pct"), default=math.inf),
        -_sort_number(metrics.get("avg_total_return_pct"), default=-math.inf),
        item["name"],
    )


def _aggregate_metrics(items: list[dict[str, Any]]) -> dict[str, float | None]:
    returns = [
        _clean_number(item.get("metrics", {}).get("total_return_pct"))
        for item in items
    ]
    drawdowns = [
        _clean_number(item.get("metrics", {}).get("max_drawdown_pct"))
        for item in items
    ]
    finite_returns = [float(value) for value in returns if isinstance(value, (int, float))]
    finite_drawdowns = [float(value) for value in drawdowns if isinstance(value, (int, float))]
    return {
        "avg_total_return_pct": (
            round(sum(finite_returns) / len(finite_returns), 10) if finite_returns else None
        ),
        "worst_max_drawdown_pct": max(finite_drawdowns) if finite_drawdowns else None,
    }
