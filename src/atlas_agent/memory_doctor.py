from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atlas_agent.safety.secrets import scan_text_for_secrets


REQUIRED_MEMORY_FILES = (
    "portfolio.md",
    "watchlist.md",
    "open_positions.md",
    "trade_journal.md",
    "strategy_rules.md",
    "daily_notes.md",
    "weekly_review.md",
    "user_profile.md",
    "preferences.md",
    "trading_style.md",
)

REQUIRED_REPORT_DIRS = (
    "agent",
    "daily",
    "weekly",
    "learning",
    "reflections",
)

REQUIRED_SKILL_DIRS = ("proposed", "active", "archived")


@dataclass(frozen=True)
class DoctorFinding:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass
class MemoryDoctorResult:
    checked_at: str
    findings: list[DoctorFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[DoctorFinding]:
        return [finding for finding in self.findings if finding.severity == "error"]

    @property
    def warnings(self) -> list[DoctorFinding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def run_memory_doctor(
    *,
    memory_dir: Path,
    pending_orders_dir: Path,
    reports_dir: Path,
    skills_dir: Path,
    stale_hours: int = 24,
) -> MemoryDoctorResult:
    result = MemoryDoctorResult(checked_at=datetime.now(UTC).replace(microsecond=0).isoformat())
    _check_memory_files(memory_dir, result)
    _check_pending_orders(pending_orders_dir, stale_hours, result)
    _check_reports_dirs(reports_dir, result)
    _check_skills_dirs(skills_dir, result)
    _check_conversation_index(memory_dir, result)
    _check_journal(memory_dir, result)
    return result


def _check_memory_files(memory_dir: Path, result: MemoryDoctorResult) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_MEMORY_FILES:
        path = memory_dir / name
        if not path.exists():
            result.findings.append(
                DoctorFinding(
                    severity="warning",
                    code="missing_memory_file",
                    message=f"missing memory file: {name}",
                    path=str(path),
                )
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            result.findings.append(
                DoctorFinding(
                    severity="error",
                    code="unreadable_memory_file",
                    message=f"failed to read memory file: {exc}",
                    path=str(path),
                )
            )
            continue
        secret_findings = scan_text_for_secrets(text)
        if secret_findings:
            result.findings.append(
                DoctorFinding(
                    severity="error",
                    code="memory_secret_detected",
                    message=f"possible secrets in {name}: {', '.join(secret_findings)}",
                    path=str(path),
                )
            )


def _check_pending_orders(pending_orders_dir: Path, stale_hours: int, result: MemoryDoctorResult) -> None:
    pending_orders_dir.mkdir(parents=True, exist_ok=True)
    threshold = datetime.now(UTC) - timedelta(hours=stale_hours)
    for path in sorted(pending_orders_dir.glob("*.json")):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified < threshold:
            result.findings.append(
                DoctorFinding(
                    severity="warning",
                    code="stale_pending_order",
                    message=f"pending order older than {stale_hours}h",
                    path=str(path),
                )
            )


def _check_reports_dirs(reports_dir: Path, result: MemoryDoctorResult) -> None:
    for name in REQUIRED_REPORT_DIRS:
        path = reports_dir / name
        if not path.exists():
            result.findings.append(
                DoctorFinding(
                    severity="warning",
                    code="missing_report_dir",
                    message=f"missing reports/{name} directory",
                    path=str(path),
                )
            )


def _check_skills_dirs(skills_dir: Path, result: MemoryDoctorResult) -> None:
    for name in REQUIRED_SKILL_DIRS:
        path = skills_dir / name
        if not path.exists():
            result.findings.append(
                DoctorFinding(
                    severity="warning",
                    code="missing_skill_dir",
                    message=f"missing skills/{name} directory",
                    path=str(path),
                )
            )


def _check_conversation_index(memory_dir: Path, result: MemoryDoctorResult) -> None:
    path = memory_dir / "conversation_index.md"
    if not path.exists():
        result.findings.append(
            DoctorFinding(
                severity="warning",
                code="missing_conversation_index",
                message="conversation index missing; create memory/conversation_index.md",
                path=str(path),
            )
        )


def _check_journal(memory_dir: Path, result: MemoryDoctorResult) -> None:
    journal = memory_dir / "trade_journal.md"
    if not journal.exists():
        result.findings.append(
            DoctorFinding(
                severity="warning",
                code="missing_journal",
                message="trade journal missing",
                path=str(journal),
            )
        )
        return
    try:
        journal.read_text(encoding="utf-8")
    except OSError as exc:
        result.findings.append(
            DoctorFinding(
                severity="error",
                code="unreadable_journal",
                message=f"failed to read trade journal: {exc}",
                path=str(journal),
            )
        )
