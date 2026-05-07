from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atlas_agent.events.log import EventLogger, generate_run_id
from atlas_agent.skills.manager import improve_proposed_skills


REAL_LOOKING_MARKERS = (
    "ALPACA_API_KEY=",
    "ALPACA_API_SECRET=",
    "BINANCE_API_KEY=",
    "BINANCE_API_SECRET=",
    "TELEGRAM_BOT_TOKEN=",
    "ACCOUNT_ID",
)


@dataclass(frozen=True)
class DemoSeedResult:
    written_paths: tuple[Path, ...]
    warning: str | None = None


def seed_demo_workspace(
    *,
    workspace_dir: Path,
    memory_dir: Path,
    reports_dir: Path,
    skills_dir: Path,
    events_dir: Path,
    force: bool = False,
) -> DemoSeedResult:
    warning = _safety_warning(workspace_dir)
    if warning and not force:
        return DemoSeedResult(
            written_paths=(),
            warning=f"{warning} Re-run with --force to seed anyway.",
        )

    written: list[Path] = []
    memory_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "reflections").mkdir(parents=True, exist_ok=True)
    (skills_dir / "proposed").mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)

    written.extend(
        _write_if_missing(
            memory_dir / "portfolio.md",
            "# Portfolio\n\n- Cash: 10000 (synthetic)\n- Equity: 10000 (synthetic)\n",
        )
    )
    written.extend(
        _write_if_missing(
            memory_dir / "watchlist.md",
            "# Watchlist\n\n- BTC-USD\n- ETH-USD\n- SPY\n",
        )
    )
    written.extend(
        _write_if_missing(
            memory_dir / "trade_journal.md",
            "# Trade Journal\n\n## 2026-01-15\n\n- Synthetic entry: cut position after risk trigger.\n",
        )
    )
    written.extend(
        _write_if_missing(
            memory_dir / "mistakes.md",
            "# Mistakes\n\n- Synthetic: entered too early on weak confirmation.\n",
        )
    )

    reflection = reports_dir / "reflections" / "demo-reflection.md"
    if not reflection.exists():
        reflection.write_text(
            "# Demo Reflection\n\n- Synthetic reflection for UI prototyping.\n",
            encoding="utf-8",
        )
        written.append(reflection)

    proposed_skill = skills_dir / "proposed" / "avoid_overtrading.md"
    if not proposed_skill.exists():
        proposed_skill.write_text(
            (
                "# Skill: avoid_overtrading\n\n"
                "## Name\navoid_overtrading\n\n"
                "## Purpose\nReduce unnecessary entries during low-conviction conditions.\n\n"
                "## When to use\nAfter two consecutive low-quality trade ideas in one session.\n\n"
                "## Inputs\ntrade_journal.md, daily_notes.md\n\n"
                "## Output format\nShort checklist before any new order.\n\n"
                "## Risk constraints\nDo not bypass RiskManager, approval gates, or kill switch.\n\n"
                "## Failure modes\nMissing context, stale journal, low confidence.\n\n"
                "## Evidence/source journal entries\ntrade_journal synthetic entry.\n\n"
                "## Last updated\n2026-01-15\n\n"
                "## Confidence level\n0.40\n\n"
                "## Owner\nAtlas Agent\n\n"
                "## Metadata\n"
                "- status: proposed\n"
                "- confidence: 0.40\n"
                "- risk_level: medium\n"
                "- evidence: trade_journal synthetic entry\n"
                "- last_updated: 2026-01-15\n"
            ),
            encoding="utf-8",
        )
        written.append(proposed_skill)

    improved = improve_proposed_skills(skills_dir)
    for path in improved:
        if path not in written:
            written.append(path)

    logger = EventLogger(events_dir)
    run_id = generate_run_id()
    logger.write(
        "agent_started",
        run_id=run_id,
        command="atlas demo seed",
        mode="paper",
        payload={"source": "demo_seed"},
    )
    logger.write(
        "memory_loaded",
        run_id=run_id,
        command="atlas demo seed",
        mode="paper",
        payload={"files": ["portfolio.md", "watchlist.md", "trade_journal.md", "mistakes.md"]},
    )
    logger.write(
        "skill_proposed",
        run_id=run_id,
        command="atlas demo seed",
        mode="paper",
        payload={"skill": "avoid_overtrading.md"},
    )
    logger.write(
        "reflection_written",
        run_id=run_id,
        command="atlas demo seed",
        mode="paper",
        payload={"path": str(reflection)},
    )
    logger.write(
        "agent_completed",
        run_id=run_id,
        command="atlas demo seed",
        mode="paper",
        payload={"status": "demo_seed_complete"},
    )

    return DemoSeedResult(written_paths=tuple(written), warning=warning)


def _write_if_missing(path: Path, content: str) -> list[Path]:
    if path.exists():
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return [path]


def _safety_warning(workspace_dir: Path) -> str | None:
    env_path = workspace_dir / ".env"
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8", errors="replace")
        if any(marker in text for marker in REAL_LOOKING_MARKERS):
            return "workspace contains potential real credentials"
    memory_portfolio = workspace_dir / "memory" / "portfolio.md"
    if memory_portfolio.exists():
        text = memory_portfolio.read_text(encoding="utf-8", errors="replace")
        if "account_id" in text.lower():
            return "workspace portfolio appears to contain account identifiers"
    return None
