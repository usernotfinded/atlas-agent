# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/robustness.py
# PURPOSE: Attacks a strategy's result to see whether it survives. Perturb the
#          inputs, shift the window, add costs — a strategy whose edge evaporates
#          under any of that was never an edge, it was a fit to one history.
# DEPS:    backtest.engine (re-runs it), backtest.metrics
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

ARTIFACT_TYPE = "paper_strategy_robustness"
SCHEMA_VERSION = 1
ALLOWED_ROBUSTNESS_STATUSES = (
    "robust_paper_follow_up",
    "regime_sensitive_needs_more_testing",
    "needs_more_testing",
    "rejected",
)
_SUMMARY_RANK = {
    "robust_paper_follow_up": 0,
    "regime_sensitive_needs_more_testing": 1,
    "needs_more_testing": 2,
    "rejected": 3,
}


def parse_fixture_list(raw: str) -> list[str]:
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
        raise ValueError("At least one regime fixture is required.")
    return items


def build_paper_strategy_robustness(
    *,
    fixture_paths: Iterable[str | Path],
    symbol: str,
    strategies: Iterable[str] | None = None,
    initial_equity: float = 10000.0,
    slippage_bps: float = 0.0,
    commission_bps: float = 0.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    strategy_ids = list(strategies) if strategies is not None else parse_strategy_list(None)
    regimes = [
        _regime_payload(path=Path(path), symbol=symbol, start_date=start_date, end_date=end_date)
        for path in fixture_paths
    ]
    if not regimes:
        raise ValueError("At least one regime fixture is required.")

    entries: list[dict[str, Any]] = []
    ranking_inputs: list[dict[str, Any]] = []

    for strategy_id in strategy_ids:
        variants = _default_variants_for(strategy_id)
        regime_results: list[dict[str, Any]] = []
        for variant_id, parameters in variants:
            for regime in regimes:
                result = _evaluate_regime_variant(
                    strategy_id=strategy_id,
                    variant_id=variant_id,
                    parameters=parameters,
                    regime=regime,
                    symbol=symbol,
                    initial_equity=initial_equity,
                    slippage_bps=slippage_bps,
                    commission_bps=commission_bps,
                    start_date=start_date,
                    end_date=end_date,
                )
                regime_results.append(result)
                ranking_inputs.append(
                    {
                        "strategy": strategy_id,
                        "variant_id": variant_id,
                        "regime": regime["name"],
                        "metrics": result["metrics"],
                        "paper_gate": result["paper_gate"],
                    }
                )

        summary = _summarize_strategy(
            regime_results=regime_results,
            regime_count=len(regimes),
            variant_count=len(variants),
        )
        entries.append(
            {
                "name": strategy_id,
                "variants_evaluated": len(variants),
                "regime_results": regime_results,
                "robustness_summary": summary,
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
        "regimes": regimes,
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


def write_strategy_robustness_reports(
    report: dict[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "strategy-robustness.json"
    markdown_path = destination / "strategy-robustness.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_strategy_robustness_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_strategy_robustness_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Strategy Robustness Report",
        "",
        (
            "**Status:** v0.6.13 planning line; paper-only; synthetic/sample-data only; "
            "offline/no-provider/no-broker; not financial advice; not live readiness; "
            "no profit guarantee; not production-ready."
        ),
        "",
        f"**Symbol:** {report['symbol']}",
        f"**Regimes:** {len(report.get('regimes', []))}",
        "",
        (
            "This multi-regime robustness report is for paper follow-up only. "
            "Robustness across deterministic synthetic fixtures does not imply future "
            "performance and does not promote any strategy to live trading, autonomous "
            "live trading, or production use."
        ),
        "",
        "## Regimes",
        "",
        "| Regime | Data source | Rows |",
        "| --- | --- | ---: |",
    ]
    for regime in report.get("regimes", []):
        lines.append(
            f"| {regime['name']} | `{regime['data_source']}` | {regime['row_count']} |"
        )

    lines.extend(
        [
            "",
            "## Strategy Matrix",
            "",
            "| Strategy | Regime | Variant | Return % | Max Drawdown % | Win Rate | Trades | Paper Gate |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for strategy in report.get("strategies", []):
        for item in strategy.get("regime_results", []):
            metrics = item.get("metrics", {})
            lines.append(
                "| {strategy} | {regime} | {variant} | {ret} | {dd} | {win} | {trades} | {gate} |".format(
                    strategy=strategy["name"],
                    regime=item["regime"],
                    variant=item["variant_id"],
                    ret=_format_pct(metrics.get("total_return_pct")),
                    dd=_format_pct(metrics.get("max_drawdown_pct")),
                    win=_format_ratio(metrics.get("win_rate")),
                    trades=metrics.get("trade_count", "n/a"),
                    gate=item["paper_gate"]["decision"],
                )
            )

    lines.extend(["", "## Robustness Summary", ""])
    for strategy in report.get("strategies", []):
        summary = strategy.get("robustness_summary", {})
        lines.append(
            "- `{name}`: `{status}` across {count} regimes - {reason}".format(
                name=strategy["name"],
                status=summary.get("paper_follow_up_status", "rejected"),
                count=summary.get("regimes_evaluated", 0),
                reason=summary.get("reason", ""),
            )
        )

    lines.extend(["", "## Ranking", ""])
    for ranked in report.get("ranking", []):
        lines.append(f"{ranked['rank']}. `{ranked['strategy']}` - {ranked['reason']}")

    lines.extend(
        [
            "",
            "## Robustness Gate Decisions",
            "",
            "- `robust_paper_follow_up`: valid across regimes for paper-only follow-up.",
            "- `regime_sensitive_needs_more_testing`: mixed valid results suggest regime sensitivity or possible overfit.",
            "- `needs_more_testing`: valid data exists, but evidence is insufficient for robust paper follow-up.",
            "- `rejected`: a run failed, metrics were invalid, or a safety blocker exists.",
            "",
            "No robustness decision is approval for live trading.",
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


def _regime_payload(
    *,
    path: Path,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    bars = load_market_data(path, symbol, start_date=start_date, end_date=end_date)
    return {
        "name": _regime_name(path),
        "data_source": str(path),
        "row_count": len(bars),
        "minimum_rows_for_candidate": MIN_SAMPLE_ROWS,
        "start": bars[0].timestamp.isoformat() if bars else None,
        "end": bars[-1].timestamp.isoformat() if bars else None,
    }


def _regime_name(path: Path) -> str:
    stem = path.stem
    if stem.startswith("ohlcv_"):
        stem = stem[len("ohlcv_") :]
    return stem.replace("-", "_")


def _evaluate_regime_variant(
    *,
    strategy_id: str,
    variant_id: str,
    parameters: dict[str, Any],
    regime: dict[str, Any],
    symbol: str,
    initial_equity: float,
    slippage_bps: float,
    commission_bps: float,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    config = BacktestConfig(
        run_id=f"paper-robust-{_slug(regime['name'])}-{_slug(variant_id)}",
        symbol=symbol,
        data_path=regime["data_source"],
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
        return _failed_regime_variant(
            regime=regime["name"],
            variant_id=variant_id,
            parameters=parameters,
            error=str(exc),
        )

    metrics = _metrics_payload(result)
    safety_blockers = _safety_blockers(result)
    return {
        "regime": regime["name"],
        "variant_id": variant_id,
        "parameters": parameters,
        "status": "evaluated",
        "metrics": metrics,
        "paper_gate": _paper_gate_robustness(
            result=result,
            metrics=metrics,
            sample_row_count=int(regime["row_count"]),
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


def _failed_regime_variant(
    *,
    regime: str,
    variant_id: str,
    parameters: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    return {
        "regime": regime,
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
            "reason": f"Backtest failed in paper robustness evaluation: {error}",
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


def _paper_gate_robustness(
    *,
    result: BacktestResult,
    metrics: dict[str, Any],
    sample_row_count: int,
    safety_blockers: list[dict[str, Any]],
) -> dict[str, str]:
    if result.status != "completed":
        return {
            "decision": "rejected",
            "reason": "Backtest did not complete; rejected for paper robustness evaluation.",
        }
    if safety_blockers:
        return {
            "decision": "rejected",
            "reason": "RiskManager blocked paper orders; rejected for paper robustness evaluation.",
        }
    if not _required_metrics_are_finite(metrics):
        return {
            "decision": "rejected",
            "reason": "Required metrics are missing or non-finite.",
        }
    if sample_row_count < MIN_SAMPLE_ROWS:
        return {
            "decision": "needs_more_testing",
            "reason": f"Regime fixture has {sample_row_count} rows; at least {MIN_SAMPLE_ROWS} rows are required.",
        }
    if metrics["max_drawdown_pct"] > PAPER_CANDIDATE_MAX_DRAWDOWN_PCT:
        return {
            "decision": "rejected",
            "reason": "Max drawdown exceeded the documented demo paper threshold.",
        }
    if int(metrics.get("trade_count") or 0) <= 0:
        return {
            "decision": "needs_more_testing",
            "reason": "No fills generated on this synthetic regime; more paper testing is required.",
        }
    if metrics["total_return_pct"] < PAPER_CANDIDATE_MIN_TOTAL_RETURN_PCT:
        return {
            "decision": "needs_more_testing",
            "reason": "Total return is below the documented demo paper threshold for this regime.",
        }
    return {
        "decision": "paper_candidate",
        "reason": "Regime run completed with finite metrics and no safety blockers; paper-only follow-up only.",
    }


def _summarize_strategy(
    *,
    regime_results: list[dict[str, Any]],
    regime_count: int,
    variant_count: int,
) -> dict[str, Any]:
    decisions = [item.get("paper_gate", {}).get("decision", "rejected") for item in regime_results]
    valid_count = sum(1 for decision in decisions if decision != "rejected")
    candidate_count = sum(1 for decision in decisions if decision == "paper_candidate")
    rejected_count = sum(1 for decision in decisions if decision == "rejected")
    all_metrics_finite = all(_required_metrics_are_finite(item.get("metrics", {})) for item in regime_results)
    all_completed = all(item.get("status") == "evaluated" for item in regime_results)
    no_safety_blockers = all(int(item.get("safety_blocker_count") or 0) == 0 for item in regime_results)
    complete_variant_count = 0
    for variant_id in sorted({item["variant_id"] for item in regime_results}):
        variant_items = [item for item in regime_results if item["variant_id"] == variant_id]
        if len(variant_items) == regime_count and all(
            item.get("paper_gate", {}).get("decision") == "paper_candidate"
            for item in variant_items
        ):
            complete_variant_count += 1

    if (
        regime_results
        and all_completed
        and all_metrics_finite
        and no_safety_blockers
        and complete_variant_count > 0
    ):
        status = "robust_paper_follow_up"
        reason = (
            "At least one variant completed every synthetic regime with paper-candidate "
            "gates; paper-only follow-up only, not live readiness."
        )
    elif rejected_count and valid_count:
        status = "regime_sensitive_needs_more_testing"
        reason = (
            "Results are mixed across regimes or variants, which may indicate regime "
            "sensitivity or one-fixture overfit; paper-only follow-up requires more testing."
        )
    elif valid_count:
        status = "needs_more_testing"
        reason = "Regime runs were valid but insufficient for robust paper follow-up."
    else:
        status = "rejected"
        reason = "No valid regime run passed the paper robustness gate."

    return {
        "regimes_evaluated": regime_count,
        "variants_evaluated": variant_count,
        "regime_result_count": len(regime_results),
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
        summary = item.get("robustness_summary", {})
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
    regime_results: list[dict[str, Any]],
) -> tuple[Any, ...]:
    summary = item.get("robustness_summary", {})
    metrics = _aggregate_metrics(regime_results)
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
