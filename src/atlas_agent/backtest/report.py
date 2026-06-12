"""Backtest report generation.

Produces JSON and Markdown research summaries from BacktestResult data.
Reports are informational only and do not constitute trading advice,
predictions, or performance guarantees.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.backtest.metrics import TradeRecord
from atlas_agent.backtest.models import BacktestResult
from atlas_agent.backtest.report_schema import REPORT_SCHEMA_VERSION


_DISCLAIMER = (
    "This is a research summary generated from a deterministic, offline, "
    "local-only backtest. It is not investment advice, a prediction, or a "
    "performance guarantee. Past simulated results do not indicate future "
    "outcomes. No real trades were executed."
)


_SENSITIVE_DIAGNOSTIC_KEYS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
    "auth_header",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(sensitive in lowered for sensitive in _SENSITIVE_DIAGNOSTIC_KEYS)


def _scrub_diagnostics(value: Any) -> Any:
    """Redact likely secrets from diagnostics while preserving structure."""
    if isinstance(value, dict):
        return {k: "[redacted]" if _is_sensitive_key(k) else _scrub_diagnostics(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_diagnostics(item) for item in value]
    return value


def render_json_report(result: BacktestResult) -> dict[str, Any]:
    """Render a BacktestResult as a JSON-serializable dict."""
    payload = result.model_dump(mode="json")
    payload["diagnostics"] = _scrub_diagnostics(payload.get("diagnostics", {}))
    payload["schema_version"] = REPORT_SCHEMA_VERSION
    payload["generated_at"] = datetime.now(UTC).isoformat()
    payload["disclaimer"] = _DISCLAIMER
    payload["report_type"] = "backtest_research_summary"
    return payload


def render_empty_json_report(*, reason: str = "No backtest data available") -> dict[str, Any]:
    """Return a minimal JSON report when no data is available."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "report_type": "backtest_research_summary",
        "status": "no_data",
        "reason": reason,
        "disclaimer": _DISCLAIMER,
    }


def render_markdown_report(result: BacktestResult) -> str:
    """Render a BacktestResult as a Markdown research summary."""
    lines: list[str] = []

    # Header
    lines.append(f"# Backtest Research Summary: {result.config.symbol}")
    lines.append("")

    # Strategy info
    strategy_name = result.strategy_metadata.get("name", result.config.strategy_mode)
    strategy_version = result.strategy_metadata.get("version", "n/a")
    lines.append(f"**Strategy:** {strategy_name} (v{strategy_version})")
    lines.append(f"**Symbol:** {result.config.symbol}")
    lines.append(f"**Run ID:** {result.run_id}")
    lines.append(f"**Status:** {result.status}")
    lines.append("")

    # Period info
    if result.equity_curve:
        first_ts = result.equity_curve[0].get("timestamp", "n/a")
        last_ts = result.equity_curve[-1].get("timestamp", "n/a")
        lines.append(f"**Period:** {first_ts} → {last_ts}")
        lines.append(f"**Observations:** {len(result.equity_curve)}")
    else:
        lines.append("**Period:** n/a")
        lines.append("**Observations:** 0")
    lines.append("")

    # Metrics table
    m = result.metrics
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Initial Equity | ${m.initial_equity:,.2f} |")
    lines.append(f"| Final Equity | ${m.final_equity:,.2f} |")
    lines.append(f"| Total Return | {m.total_return_pct:.2f}% |")
    if m.annualized_return_pct is not None:
        lines.append(f"| Annualized Return | {m.annualized_return_pct:.2f}% |")
    lines.append(f"| Max Drawdown | {m.max_drawdown_pct:.2f}% |")
    lines.append(f"| Trade Count | {m.trade_count} |")
    if m.win_rate is not None:
        lines.append(f"| Win Rate | {m.win_rate:.2%} |")
    if m.sharpe_ratio is not None:
        lines.append(f"| Sharpe Ratio | {m.sharpe_ratio:.4f} |")
    if m.exposure_time_pct is not None:
        lines.append(f"| Exposure Time | {m.exposure_time_pct:.2f}% |")
    if m.buy_and_hold_return_pct is not None:
        lines.append(f"| Buy & Hold Return | {m.buy_and_hold_return_pct:.2f}% |")
    lines.append("")

    # Trade Metrics
    sell_fills = [f for f in result.fills if f.side == "sell"]
    lines.append("## Trade Metrics")
    lines.append("")
    if sell_fills:
        realized_pnls = [f.realized_pnl for f in sell_fills]
        winning = sum(1 for p in realized_pnls if p > 0)
        losing = sum(1 for p in realized_pnls if p < 0)
        best_pnl = max(realized_pnls)
        worst_pnl = min(realized_pnls)
        avg_pnl = sum(realized_pnls) / len(realized_pnls)
        lines.append("| Metric | Value |")
        lines.append("| --- | ---: |")
        lines.append(f"| Realized Fill Count | {len(sell_fills)} |")
        lines.append(f"| Winning Realized Fills | {winning} |")
        lines.append(f"| Losing Realized Fills | {losing} |")
        lines.append(f"| Best Realized PnL | ${best_pnl:,.2f} |")
        lines.append(f"| Worst Realized PnL | ${worst_pnl:,.2f} |")
        lines.append(f"| Average Realized PnL | ${avg_pnl:,.2f} |")
        if m.best_trade_pct is not None:
            lines.append(f"| Best Trade % | {m.best_trade_pct:.2f}% |")
        if m.worst_trade_pct is not None:
            lines.append(f"| Worst Trade % | {m.worst_trade_pct:.2f}% |")
        if m.average_trade_pct is not None:
            lines.append(f"| Average Trade % | {m.average_trade_pct:.2f}% |")
    else:
        lines.append("No realized trades recorded.")
    lines.append("")

    # Benchmark
    if result.benchmark:
        bm_name = result.benchmark.get("benchmark_id", "n/a")
        bm_return = result.benchmark.get("return_pct")
        lines.append("## Benchmark")
        lines.append("")
        lines.append(f"**Benchmark:** {bm_name}")
        if bm_return is not None:
            lines.append(f"**Benchmark Return:** {bm_return:.2f}%")
        else:
            lines.append("**Benchmark Return:** n/a")
        lines.append("")

    # Diagnostics
    diagnostics = _scrub_diagnostics(result.diagnostics or {})
    lines.append("## Diagnostics")
    lines.append("")
    if diagnostics.get("redacted"):
        lines.append("Diagnostics redacted.")
    elif not diagnostics:
        lines.append("No diagnostics recorded.")
    else:
        blocked_orders = diagnostics.get("blocked_orders", [])
        strategy_validation = diagnostics.get("strategy_validation", {})
        lines.append(f"**Blocked Orders:** {len(blocked_orders)}")
        if strategy_validation:
            lines.append(f"**Strategy Validation:** {strategy_validation.get('status', 'n/a')}")
            issues = strategy_validation.get("issues", [])
            if issues:
                lines.append("")
                lines.append("### Validation Issues")
                lines.append("")
                for issue in issues:
                    severity = issue.get("severity", "unknown")
                    message = issue.get("message", "")
                    lines.append(f"- [{severity}] {message}")
        other = {k: v for k, v in diagnostics.items() if k not in ("blocked_orders", "strategy_validation")}
        if other:
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(other, indent=2))
            lines.append("```")
    lines.append("")

    # Fills Summary
    lines.append("## Fills Summary")
    lines.append("")
    if result.fills:
        buy_fills = [f for f in result.fills if f.side == "buy"]
        sell_fills = [f for f in result.fills if f.side == "sell"]
        total_notional = sum(f.notional for f in result.fills)
        total_realized_pnl = sum(f.realized_pnl for f in result.fills)
        total_commission = sum(f.commission for f in result.fills)
        lines.append(f"**Total Fills:** {len(result.fills)}")
        lines.append(f"**Buy Fills:** {len(buy_fills)}")
        lines.append(f"**Sell Fills:** {len(sell_fills)}")
        lines.append(f"**Total Notional:** ${total_notional:,.2f}")
        lines.append(f"**Total Realized PnL:** ${total_realized_pnl:,.2f}")
        lines.append(f"**Total Commission:** ${total_commission:,.2f}")
        lines.append("")
        lines.append("| Side | Symbol | Quantity | Price | Notional | Realized PnL | Commission |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for f in result.fills:
            lines.append(
                f"| {f.side} | {f.symbol} | {f.quantity:,.4f} | ${f.price:,.2f} | "
                f"${f.notional:,.2f} | ${f.realized_pnl:,.2f} | ${f.commission:,.2f} |"
            )
    else:
        lines.append("No fills recorded.")
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append(f"*{_DISCLAIMER}*")
    lines.append("")

    return "\n".join(lines)


def render_empty_markdown_report(*, reason: str = "No backtest data available") -> str:
    """Return a minimal Markdown report when no data is available."""
    lines = [
        "# Backtest Research Summary",
        "",
        f"**Status:** {reason}",
        "",
        "No data was available to generate a backtest summary.",
        "",
        "---",
        "",
        f"*{_DISCLAIMER}*",
        "",
    ]
    return "\n".join(lines)


def write_backtest_report(
    *,
    payload: dict[str, Any],
    trades: list[TradeRecord],
    output_dir: str | Path,
    stem: str,
) -> tuple[Path, Path, Path]:
    """Write JSON, Markdown, and CSV trade files to output_dir.

    This is the legacy write API used by earlier engine integrations.
    Prefer render_json_report / render_markdown_report for new code.
    """
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(), **payload}
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"
    csv_path = report_dir / f"{stem}-trades.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_legacy_markdown(payload), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["side", "quantity", "price", "notional", "realized_pnl"],
        )
        writer.writeheader()
        for trade in trades:
            writer.writerow(asdict(trade))
    return json_path, md_path, csv_path


def write_report_from_result(
    result: BacktestResult,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write JSON and Markdown report files from a BacktestResult.

    Returns (json_path, markdown_path).
    """
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    json_payload = render_json_report(result)
    md_content = render_markdown_report(result)

    json_path = report_dir / "result.json"
    md_path = report_dir / "report.md"

    json_path.write_text(
        json.dumps(json_payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    md_path.write_text(md_content, encoding="utf-8")
    return json_path, md_path


def _legacy_markdown(payload: dict[str, Any]) -> str:
    """Generate legacy markdown table from a raw payload dict."""
    metrics = payload["metrics"]
    lines = [
        f"# Backtest Report: {payload['symbol']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in metrics.items():
        if isinstance(value, float):
            rendered = f"{value:.4f}"
        else:
            rendered = str(value)
        lines.append(f"| {key} | {rendered} |")
    return "\n".join(lines) + "\n"
