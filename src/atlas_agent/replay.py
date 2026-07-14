# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    replay.py
# PURPOSE: Reconstructs the story of a past agent run from its event log — what it
#          saw, what it decided, what risk said, what the broker did. This is the
#          post-mortem tool: it answers "why did it place that order?".
# DEPS:    atlas_agent.events.log (event source)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas_agent.events.log import list_event_files, read_event_file


# ==============================================================================
# SUMMARY MODEL
# ==============================================================================

@dataclass
class ReplaySummary:
    source: str
    run_id: str | None

    # These buckets mirror the agent's pipeline stages in order — context, market,
    # decision, risk, order, artifacts. Keeping the field order aligned with the
    # real execution order is what makes a rendered summary readable top to bottom.
    inputs_context: list[str] = field(default_factory=list)
    market_state: list[str] = field(default_factory=list)
    decision: list[str] = field(default_factory=list)
    risk_outcome: list[str] = field(default_factory=list)
    order_outcome: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    # Gaps in the chain above, not exceptions. See summarize_run().
    warnings: list[str] = field(default_factory=list)


# ==============================================================================
# REPLAY ENTRY POINTS
# ==============================================================================

def replay_last_run(events_dir: str | Path = "events") -> ReplaySummary | None:
    grouped = _group_events_by_run(events_dir)
    if not grouped:
        return None
    latest_run_id, events = max(
        grouped.items(),
        key=lambda item: _event_timestamp(item[1][-1]),
    )
    return summarize_run(events, source=f"{events_dir}/latest", run_id=latest_run_id)


def replay_from_path(path: str | Path, events_dir: str | Path = "events") -> ReplaySummary | None:
    target = Path(path)
    if target.suffix == ".jsonl":
        events = read_event_file(target)
        if not events:
            return None
        grouped = _group_by_run_id(events)
        if grouped:
            latest_run_id, run_events = max(
                grouped.items(),
                key=lambda item: _event_timestamp(item[1][-1]),
            )
            return summarize_run(run_events, source=str(target), run_id=latest_run_id)
        return summarize_run(events, source=str(target), run_id=None)
    if target.suffix == ".md":
        if not target.exists():
            return None
        # A rendered report is a lossy artefact: it has no event timeline, so we can
        # only echo its head back. Flagged explicitly so nobody reads the empty
        # risk/decision buckets below as "the agent skipped those stages".
        text = target.read_text(encoding="utf-8", errors="replace")
        summary = ReplaySummary(source=str(target), run_id=None)
        summary.inputs_context.append("report-only replay; event timeline unavailable")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        summary.artifacts.extend(lines[:8])
        return summary
    # fallback: attempt latest run
    return replay_last_run(events_dir)


# ==============================================================================
# EVENT TIMELINE → SUMMARY
# ==============================================================================

def summarize_run(events: list[dict[str, Any]], *, source: str, run_id: str | None) -> ReplaySummary:
    summary = ReplaySummary(source=source, run_id=run_id)
    for event in events:
        event_type = str(event.get("event_type", ""))
        payload = event.get("payload", {})
        if event_type == "agent_started":
            summary.inputs_context.append(
                f"command={event.get('command')} mode={event.get('mode')}"
            )
        elif event_type == "memory_loaded":
            files = payload.get("files")
            if files:
                summary.inputs_context.append(f"memory files: {files}")
        elif event_type == "market_state_detected":
            summary.market_state.append(f"state={payload.get('state', 'unknown')}")
        elif event_type in {"decision_proposed", "model_guidance_loaded"}:
            summary.decision.append(f"{event_type}: {payload}")
        elif event_type in {"risk_approved", "risk_rejected"}:
            summary.risk_outcome.append(f"{event_type}: {payload}")
        elif event_type in {"order_created", "order_pending_approval", "order_executed", "order_rejected"}:
            summary.order_outcome.append(f"{event_type}: {payload}")
        elif event_type in {"memory_updated", "reflection_written", "skill_proposed", "skill_improved"}:
            summary.artifacts.append(f"{event_type}: {payload}")
        elif event_type in {"agent_failed"}:
            summary.warnings.append(f"agent_failed: {payload}")
        elif event_type in {"agent_completed"}:
            summary.artifacts.append(f"agent_completed: {payload}")

    # --- Chain-integrity checks ---
    # These two warnings are the whole point of replay. A decision that never
    # reached risk, or an order that never reached a terminal state, means the
    # pipeline was interrupted — a crash, a kill switch, a lost process. Silence
    # here would let a half-executed run look identical to a clean one.
    if not summary.risk_outcome and summary.decision:
        summary.warnings.append("decision present without risk outcome")
    if any("order_created" in entry for entry in summary.order_outcome) and not any(
        marker in " ".join(summary.order_outcome)
        for marker in ("order_executed", "order_rejected", "order_pending_approval")
    ):
        summary.warnings.append("order created without final order outcome")
    return summary


# ==============================================================================
# EVENT GROUPING HELPERS
# ==============================================================================

def _group_events_by_run(events_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for file_path in list_event_files(events_dir):
        for event in read_event_file(file_path):
            run_id = event.get("run_id")
            if isinstance(run_id, str) and run_id:
                grouped.setdefault(run_id, []).append(event)
    for run_events in grouped.values():
        run_events.sort(key=_event_timestamp)
    return grouped


def _group_by_run_id(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        run_id = event.get("run_id")
        if isinstance(run_id, str) and run_id:
            grouped.setdefault(run_id, []).append(event)
    for run_events in grouped.values():
        run_events.sort(key=_event_timestamp)
    return grouped


def _event_timestamp(event: dict[str, Any]) -> str:
    # Sorts lexicographically because timestamps are ISO-8601 UTC (see output.now_iso),
    # where string order and chronological order coincide. An untimestamped event
    # sorts to the front rather than blowing up the sort.
    value = event.get("timestamp")
    if isinstance(value, str):
        return value
    return ""
