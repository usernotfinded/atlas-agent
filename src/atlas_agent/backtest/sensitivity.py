# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/sensitivity.py
# PURPOSE: Sweeps a strategy's parameters and reports how much the result moves. A
#          strategy that only works at period=14 and collapses at 13 and 15 is
#          overfitted — this is the module that catches that.
# DEPS:    backtest.engine, backtest.strategy (the parameter specs it sweeps)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Dict, List

from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.engine import BacktestEngine
from atlas_agent.backtest.models import BacktestConfig, BacktestResult
from atlas_agent.backtest.registry import list_strategies
from atlas_agent.backtest.evaluation import (
    parse_strategy_list,
    MIN_SAMPLE_ROWS,
    PAPER_CANDIDATE_MAX_DRAWDOWN_PCT,
    PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT,
    _required_metrics_are_finite,
    _format_pct,
    _format_ratio,
    _metrics_payload,
    _safety_blockers,
    _slug,
    _clean_number,
    _DECISION_RANK,
    _sort_number,
)

ARTIFACT_TYPE = "paper_strategy_sensitivity"
SCHEMA_VERSION = 1

def _default_variants_for(strategy_id: str) -> list[tuple[str, dict[str, Any]]]:
    if strategy_id == "moving_average_cross":
        return [
            ("moving_average_cross__short_3__long_7", {"short_window": 3, "long_window": 7}),
            ("moving_average_cross__short_5__long_10", {"short_window": 5, "long_window": 10}),
            ("moving_average_cross__short_7__long_14", {"short_window": 7, "long_window": 14}),
        ]
    elif strategy_id == "rsi_mean_reversion":
        return [
            ("rsi_mean_reversion__p7_30_70", {"period": 7, "oversold": 30.0, "overbought": 70.0}),
            ("rsi_mean_reversion__p14_30_70", {"period": 14, "oversold": 30.0, "overbought": 70.0}),
            ("rsi_mean_reversion__p14_35_65", {"period": 14, "oversold": 35.0, "overbought": 65.0}),
        ]
    return [(f"{strategy_id}__baseline", {})]

def build_paper_strategy_sensitivity(
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
    """Evaluate strategy parameter sensitivity through the deterministic paper backtest engine."""
    data_source = str(data_path)
    strategy_ids = list(strategies) if strategies is not None else parse_strategy_list(None)
    bars = load_market_data(data_source, symbol, start_date=start_date, end_date=end_date)
    sample_row_count = len(bars)
    sample = {
        "row_count": sample_row_count,
        "minimum_rows_for_candidate": MIN_SAMPLE_ROWS,
        "start": bars[0].timestamp.isoformat() if bars else None,
        "end": bars[-1].timestamp.isoformat() if bars else None,
    }

    entries: list[dict[str, Any]] = []
    ranking_entries: list[dict[str, Any]] = []

    for strategy_id in strategy_ids:
        variants = _default_variants_for(strategy_id)
        evaluated_variants = []
        valid_variant_count = 0
        
        for variant_id, params in variants:
            res = _evaluate_variant(
                strategy_id=strategy_id,
                variant_id=variant_id,
                parameters=params,
                data_source=data_source,
                symbol=symbol,
                sample_row_count=sample_row_count,
                initial_equity=initial_equity,
                slippage_bps=slippage_bps,
                commission_bps=commission_bps,
                start_date=start_date,
                end_date=end_date,
            )
            evaluated_variants.append(res)
            
            # Prepare for ranking
            if res["status"] == "evaluated" and res["paper_gate"]["decision"] != "rejected":
                valid_variant_count += 1
            
            # Reformat to push to flattened ranking list
            ranking_entries.append({
                "strategy": strategy_id,
                "variant_id": variant_id,
                "metrics": res["metrics"],
                "paper_gate": res["paper_gate"]
            })

        # Summarize strategy sensitivity
        stable_enough = valid_variant_count > 0 and (valid_variant_count > 1 or len(variants) == 1)
        reason = "Stable variants evaluated." if stable_enough else "Not enough stable variants."

        entries.append({
            "name": strategy_id,
            "variants": evaluated_variants,
            "sensitivity_summary": {
                "variants_evaluated": len(variants),
                "stable_enough_for_paper_follow_up": stable_enough,
                "reason": reason
            }
        })

    ranking = _rank_sensitivity_entries(ranking_entries)

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

def write_strategy_sensitivity_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "strategy-sensitivity.json"
    markdown_path = destination / "strategy-sensitivity.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_strategy_sensitivity_markdown(report), encoding="utf-8")
    return json_path, markdown_path

def render_strategy_sensitivity_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Strategy Sensitivity Matrix",
        "",
        "**Status:** v0.6.13 planning line; paper-only; sample-data only; "
        "offline/no-provider/no-broker; not financial advice; not live "
        "readiness; no profit guarantee; not production-ready.",
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Data source:** `{report['data_source']}`",
        f"**Rows:** {report.get('sample', {}).get('row_count', 0)}",
        "",
        "This ranking and sensitivity evaluation is for paper follow-up only. It does not promote any "
        "strategy to live trading, autonomous live trading, or production use. Parameter stability does not imply future performance.",
        "",
        "## Variants Matrix",
        "",
        "| Strategy | Variant | Return % | Max Drawdown % | Win Rate | Trades | Paper Gate |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    
    for strategy in report["strategies"]:
        for item in strategy["variants"]:
            metrics = item.get("metrics", {})
            win_rate = metrics.get("win_rate")
            lines.append(
                "| {name} | {variant} | {ret} | {dd} | {win} | {trades} | {gate} |".format(
                    name=strategy["name"],
                    variant=item["variant_id"],
                    ret=_format_pct(metrics.get("total_return_pct")),
                    dd=_format_pct(metrics.get("max_drawdown_pct")),
                    win=_format_ratio(win_rate),
                    trades=metrics.get("trade_count", "n/a"),
                    gate=item["paper_gate"]["decision"],
                )
            )

    lines.extend(["", "## Ranking", ""])
    for ranked in report["ranking"]:
        lines.append(f"{ranked['rank']}. `{ranked['strategy']}` (`{ranked['variant_id']}`) - {ranked['reason']}")

    lines.extend([
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
    ])
    return "\n".join(lines)


def _evaluate_variant(
    *,
    strategy_id: str,
    variant_id: str,
    parameters: dict[str, Any],
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
        run_id=f"paper-sens-{_slug(variant_id)}",
        symbol=symbol,
        data_path=data_source,
        initial_equity=initial_equity,
        slippage_bps=slippage_bps,
        commission_bps=commission_bps,
        start_date=start_date,
        end_date=end_date,
        strategy_mode=strategy_id,
        strategy_parameters=parameters,
        benchmark_mode="buy_and_hold",
        risk_enabled=True,
        kill_switch_state=False,
    )
    try:
        result = BacktestEngine(config).run()
    except Exception as exc:
        return _failed_variant(variant_id=variant_id, parameters=parameters, error=str(exc))

    metrics = _metrics_payload(result)
    safety_blockers = _safety_blockers(result)
    paper_gate = _paper_gate_sens(
        result=result,
        metrics=metrics,
        sample_row_count=sample_row_count,
        safety_blockers=safety_blockers,
    )
    return {
        "variant_id": variant_id,
        "parameters": parameters,
        "status": "evaluated",
        "metrics": metrics,
        "paper_gate": paper_gate,
        "live_ready": False,
    }


def _failed_variant(*, variant_id: str, parameters: dict[str, Any], error: str) -> dict[str, Any]:
    return {
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
            "reason": f"Backtest failed in paper evaluation: {error}",
        },
        "live_ready": False,
    }


def _paper_gate_sens(
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
            "reason": "RiskManager blocked orders.",
        }
    if not _required_metrics_are_finite(metrics):
        return {
            "decision": "rejected",
            "reason": "Required metrics missing or non-finite.",
        }
    if sample_row_count < MIN_SAMPLE_ROWS:
        return {
            "decision": "needs_more_testing",
            "reason": f"Sample has {sample_row_count} rows; {MIN_SAMPLE_ROWS} required.",
        }
    if metrics["max_drawdown_pct"] > PAPER_CANDIDATE_MAX_DRAWDOWN_PCT:
        return {
            "decision": "rejected",
            "reason": "Max drawdown exceeded threshold.",
        }
    if int(metrics.get("trade_count") or 0) <= 0:
        return {
            "decision": "needs_more_testing",
            "reason": "No fills generated.",
        }
    if metrics["total_return_pct"] < PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT:
        return {
            "decision": "needs_more_testing",
            "reason": "Total return below threshold.",
        }
    return {
        "decision": "paper_candidate",
        "reason": "Backtest completed with finite metrics, no blockers, within thresholds; paper-only follow-up.",
    }


def _rank_sensitivity_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(entries, key=lambda item: (
        _DECISION_RANK.get(item.get("paper_gate", {}).get("decision", "rejected"), _DECISION_RANK["rejected"]),
        _sort_number(item.get("metrics", {}).get("max_drawdown_pct"), default=math.inf),
        -_sort_number(item.get("metrics", {}).get("total_return_pct"), default=-math.inf),
        -_sort_number(item.get("metrics", {}).get("win_rate"), default=-math.inf),
        -int(item.get("metrics", {}).get("trade_count") or 0),
        item["variant_id"]
    ))
    output: list[dict[str, Any]] = []
    for index, item in enumerate(ranked, start=1):
        metrics = item.get("metrics", {})
        decision = item.get("paper_gate", {}).get("decision", "rejected")
        output.append({
            "rank": index,
            "strategy": item["strategy"],
            "variant_id": item["variant_id"],
            "decision": decision,
            "reason": (
                f"decision={decision}; total_return={_format_pct(metrics.get('total_return_pct'))}; "
                f"max_drawdown={_format_pct(metrics.get('max_drawdown_pct'))}"
            ),
        })
    return output

