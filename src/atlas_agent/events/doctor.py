from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas_agent.events.log import list_event_files, read_event_file
from atlas_agent.events.schema import find_likely_secrets, validate_event_record


@dataclass(frozen=True)
class EventIssue:
    severity: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None


@dataclass
class EventDoctorResult:
    files_scanned: int = 0
    events_scanned: int = 0
    errors: list[EventIssue] = field(default_factory=list)
    warnings: list[EventIssue] = field(default_factory=list)
    run_ids: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.errors


def diagnose_events(events_dir: str | Path = "events") -> EventDoctorResult:
    result = EventDoctorResult()
    files = list_event_files(events_dir)
    result.files_scanned = len(files)
    runs: dict[str, list[dict[str, Any]]] = {}

    for file_path in files:
        try:
            events = read_event_file(file_path)
        except ValueError as exc:
            result.errors.append(
                EventIssue(
                    severity="error",
                    code="invalid_jsonl",
                    message=str(exc),
                    path=str(file_path),
                )
            )
            continue
        for index, event in enumerate(events, start=1):
            result.events_scanned += 1
            for error in validate_event_record(event):
                result.errors.append(
                    EventIssue(
                        severity="error",
                        code="invalid_event",
                        message=error,
                        path=str(file_path),
                        line=index,
                    )
                )
            for finding in find_likely_secrets(event):
                result.errors.append(
                    EventIssue(
                        severity="error",
                        code="secret_detected",
                        message=finding,
                        path=str(file_path),
                        line=index,
                    )
                )
            run_id = event.get("run_id")
            if isinstance(run_id, str) and run_id.strip():
                runs.setdefault(run_id, []).append(event)

    result.run_ids = set(runs.keys())
    _evaluate_run_coherence(runs, result)
    return result


def _evaluate_run_coherence(
    runs: dict[str, list[dict[str, Any]]],
    result: EventDoctorResult,
) -> None:
    for run_id, events in runs.items():
        types = [str(event.get("event_type", "")) for event in events]
        if "agent_started" in types and not any(t in {"agent_completed", "agent_failed"} for t in types):
            result.warnings.append(
                EventIssue(
                    severity="warning",
                    code="incomplete_run",
                    message="run has agent_started without agent_completed/agent_failed",
                    path=run_id,
                )
            )
        if "decision_proposed" in types and not any(t in {"risk_approved", "risk_rejected"} for t in types):
            result.warnings.append(
                EventIssue(
                    severity="warning",
                    code="decision_without_risk",
                    message="decision_proposed without risk_approved/risk_rejected in run",
                    path=run_id,
                )
            )
        if "order_created" in types and not any(
            t in {"order_executed", "order_rejected", "order_pending_approval"} for t in types
        ):
            result.warnings.append(
                EventIssue(
                    severity="warning",
                    code="order_without_outcome",
                    message="order_created without order outcome in run",
                    path=run_id,
                )
            )
