from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas_agent.events.log import EventLogger, generate_run_id

if TYPE_CHECKING:
    from atlas_agent.learning.memory_index import MemoryIndexResult
    from atlas_agent.research.research_report import ResearchReport


RESEARCH_DIR = Path(".atlas") / "research"

SUPPORTED_RESEARCH_PROVIDERS = {"deterministic"}


class ResearchSessionError(RuntimeError):
    pass


class UnsupportedResearchProviderError(ResearchSessionError):
    pass


@dataclass(frozen=True)
class ResearchArtifact:
    symbol: str
    mode: str
    provider: str
    summary: str
    thesis: str
    market_context: str
    risks: list[str]
    invalidation_conditions: list[str]
    paper_only_plan: str
    citations: tuple[str, ...]
    memory_hits: list[dict[str, str]]
    warnings: list[str]
    run_id: str
    created_at: datetime
    artifact_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DeterministicResearchProvider:
    """A deterministic, local, network-free research provider."""

    def research_market(self, symbol: str) -> "ResearchReport":
        from atlas_agent.research.research_report import ResearchReport

        return ResearchReport(
            symbol=symbol.upper(),
            provider="deterministic",
            summary=f"Deterministic market context for {symbol.upper()}. No external data queried.",
        )


def sanitize_symbol(symbol: str) -> str:
    """Return a filesystem-safe sanitized symbol. Blocks path traversal."""
    if not symbol:
        raise ResearchSessionError("symbol must not be empty")
    if "/" in symbol or "\\" in symbol or symbol.startswith(".") or ".." in symbol:
        raise ResearchSessionError(f"symbol contains path traversal characters: {symbol}")
    sanitized = ""
    for ch in symbol:
        if ch.isalnum() or ch in "-_":
            sanitized += ch
        elif ch == "." and sanitized:
            sanitized += ch
    if not sanitized:
        raise ResearchSessionError(f"symbol contains no safe characters: {symbol}")
    return sanitized.upper()


def _default_snippet_builder(content: str, index: int, length: int) -> str:
    start = max(0, index - 40)
    end = min(len(content), index + length + 40)
    snippet = content[start:end].replace("\n", " ")
    return snippet.strip()


def _safe_memory_hit(hit: "MemoryIndexResult") -> dict[str, str]:
    rel = Path(hit.path).name
    return {"file": rel, "snippet": hit.snippet[:200]}


def _resolve_provider(provider_name: str | None) -> Any:
    if provider_name is None or provider_name == "deterministic":
        return DeterministicResearchProvider()
    if provider_name not in SUPPORTED_RESEARCH_PROVIDERS:
        raise UnsupportedResearchProviderError(
            f"unsupported_research_provider: {provider_name}"
        )
    return DeterministicResearchProvider()


def run_research_session(
    symbol: str,
    workspace_path: Path,
    *,
    memory_dir: Path | None = None,
    event_logger: EventLogger | None = None,
    provider: Any | None = None,
    provider_name: str | None = None,
    use_memory: bool = True,
) -> ResearchArtifact:
    """Run a paper-only research session and persist a safe artifact.

    This never touches broker submit paths.
    """
    safe_symbol = sanitize_symbol(symbol)
    run_id = generate_run_id()
    created_at = datetime.now(UTC)
    warnings: list[str] = []

    # Resolve provider
    if provider is not None:
        research_provider = provider
    else:
        research_provider = _resolve_provider(provider_name)
    report: ResearchReport = research_provider.research_market(safe_symbol)

    # Optional memory search — never fails
    memory_hits: list[dict[str, str]] = []
    if use_memory and memory_dir is not None and memory_dir.exists():
        try:
            from atlas_agent.learning.memory_index import search_memory_index

            raw_hits = search_memory_index(
                memory_dir,
                query=safe_symbol,
                snippet_builder=_default_snippet_builder,
                max_results=5,
            )
            if raw_hits is not None:
                memory_hits = [_safe_memory_hit(h) for h in raw_hits]
        except Exception:
            warnings.append("memory_search_failed")

    # Build artifact with stable shape
    artifact = ResearchArtifact(
        symbol=safe_symbol,
        mode="paper",
        provider=report.provider,
        summary=report.summary,
        thesis="No directional thesis generated. This is an analysis-only artifact.",
        market_context="No live market data queried. Deterministic local context only.",
        risks=[
            "Research artifacts are not trading signals.",
            "Deterministic provider does not query live prices.",
        ],
        invalidation_conditions=[
            "Artifact becomes stale when market conditions change.",
            "Deterministic provider does not adapt to news or events.",
        ],
        paper_only_plan="Review artifact before any paper or live workflow. Do not execute orders based solely on this artifact.",
        citations=report.citations,
        memory_hits=memory_hits,
        warnings=warnings,
        run_id=run_id,
        created_at=created_at,
        artifact_path="",
        metadata={"provider_requested": provider_name or "deterministic"},
    )

    # Persist JSON artifact
    artifact_dir = workspace_path / RESEARCH_DIR / safe_symbol
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = artifact_dir / f"{run_id}.json"
    _write_safe_json(artifact_file, artifact)

    artifact = ResearchArtifact(
        symbol=artifact.symbol,
        mode=artifact.mode,
        provider=artifact.provider,
        summary=artifact.summary,
        thesis=artifact.thesis,
        market_context=artifact.market_context,
        risks=artifact.risks,
        invalidation_conditions=artifact.invalidation_conditions,
        paper_only_plan=artifact.paper_only_plan,
        citations=artifact.citations,
        memory_hits=artifact.memory_hits,
        warnings=artifact.warnings,
        run_id=artifact.run_id,
        created_at=artifact.created_at,
        artifact_path=artifact_file.relative_to(workspace_path).as_posix(),
        metadata=artifact.metadata,
    )

    # Log event with safe payload
    if event_logger is not None:
        payload = {
            "symbol": safe_symbol,
            "mode": "paper",
            "provider": report.provider,
            "artifact_path": artifact.artifact_path,
            "status": "created",
        }
        event_logger.write(
            "research_run_created",
            run_id=run_id,
            command="atlas research run",
            mode="paper",
            payload=payload,
        )

    return artifact


def validate_run_id(run_id: str) -> str:
    """Return a safe run_id or raise ResearchSessionError."""
    if not run_id:
        raise ResearchSessionError("run_id must not be empty")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
    if not all(ch in allowed for ch in run_id):
        raise ResearchSessionError("run_id contains unsafe characters")
    if len(run_id) > 80:
        raise ResearchSessionError("run_id exceeds maximum length")
    return run_id


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_research_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe)
    else:
        search_dirs = [d for d in research_dir.iterdir() if d.is_dir()]

    items: list[dict[str, Any]] = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                # Malformed JSON: skip in list mode with a safe sentinel
                items.append(
                    {
                        "run_id": path.stem,
                        "symbol": directory.name,
                        "created_at": "",
                        "artifact_path": path.relative_to(workspace_path).as_posix(),
                        "provider": "unknown",
                        "warnings_count": 1,
                        "_malformed": True,
                    }
                )
                continue
            # Only use computed workspace-relative path
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "run_id": data.get("run_id", path.stem),
                    "symbol": data.get("symbol", directory.name),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                    "provider": data.get("provider", "unknown"),
                    "warnings_count": len(data.get("warnings", [])),
                }
            )

    # Sort by created_at descending; malformed items sort to bottom
    def _sort_key(item: dict[str, Any]) -> str:
        return item["created_at"] if not item.get("_malformed") else ""

    items.sort(key=_sort_key, reverse=True)
    return items


def iter_plan_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of plan artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "plans")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                plans_dir = sym_dir / "plans"
                if plans_dir.exists():
                    search_dirs.append(plans_dir)

    items: list[dict[str, Any]] = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                items.append(
                    {
                        "plan_id": path.stem,
                        "symbol": directory.parent.name,
                        "created_at": "",
                        "artifact_path": path.relative_to(workspace_path).as_posix(),
                        "provider": "unknown",
                        "warnings_count": 1,
                        "_malformed": True,
                    }
                )
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "plan_id": data.get("plan_id", path.stem),
                    "source_run_id": data.get("source_run_id", ""),
                    "symbol": data.get("symbol", directory.parent.name),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                    "provider": data.get("provider", "unknown"),
                    "warnings_count": len(data.get("warnings", [])),
                }
            )

    def _sort_key(item: dict[str, Any]) -> str:
        return item["created_at"] if not item.get("_malformed") else ""

    items.sort(key=_sort_key, reverse=True)
    return items


def summarize_research_workspace(
    workspace_path: Path,
) -> dict[str, Any]:
    """Return a compact read-only summary of research artifacts and plans.

    No artifact creation. No broker calls. No execution paths.
    """
    research_items = iter_research_artifacts(workspace_path)
    plan_items = iter_plan_artifacts(workspace_path)

    research_count = sum(1 for r in research_items if not r.get("_malformed"))
    plan_count = sum(1 for p in plan_items if not p.get("_malformed"))

    # Group research by symbol
    by_symbol: dict[str, dict[str, Any]] = {}
    for item in research_items:
        if item.get("_malformed"):
            continue
        sym = item["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {
                "symbol": sym,
                "research_count": 0,
                "plan_count": 0,
                "latest_research_run_id": None,
                "latest_research_path": None,
                "latest_plan_id": None,
                "latest_plan_path": None,
            }
        by_symbol[sym]["research_count"] += 1
        if by_symbol[sym]["latest_research_run_id"] is None:
            by_symbol[sym]["latest_research_run_id"] = item["run_id"]
            by_symbol[sym]["latest_research_path"] = item["artifact_path"]

    # Group plans by symbol
    for item in plan_items:
        if item.get("_malformed"):
            continue
        sym = item["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {
                "symbol": sym,
                "research_count": 0,
                "plan_count": 0,
                "latest_research_run_id": None,
                "latest_research_path": None,
                "latest_plan_id": None,
                "latest_plan_path": None,
            }
        by_symbol[sym]["plan_count"] += 1
        if by_symbol[sym]["latest_plan_id"] is None:
            by_symbol[sym]["latest_plan_id"] = item["plan_id"]
            by_symbol[sym]["latest_plan_path"] = item["artifact_path"]

    symbols = sorted(by_symbol.values(), key=lambda d: d["symbol"])

    # Warnings: count malformed
    malformed_warnings = 0
    for item in research_items:
        if item.get("_malformed"):
            malformed_warnings += 1
    for item in plan_items:
        if item.get("_malformed"):
            malformed_warnings += 1

    warnings: list[str] = []
    if malformed_warnings:
        warnings.append(f"malformed artifacts skipped: {malformed_warnings}")

    return {
        "research_count": research_count,
        "plan_count": plan_count,
        "symbols": symbols,
        "warnings": warnings,
    }


def load_research_artifact(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a research artifact JSON safely.

    Returns a dict with a computed workspace-relative artifact_path.
    """
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("artifact_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("artifact_malformed")
    # Enforce workspace-relative path in output
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    return data


def find_research_artifact_by_run_id(
    workspace_path: Path, run_id: str
) -> Path | None:
    """Find exactly one artifact by run_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_run_id = validate_run_id(run_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for directory in research_dir.iterdir():
        if not directory.is_dir():
            continue
        candidate = directory / f"{safe_run_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_run_id")
    return matches[0]


@dataclass(frozen=True)
class PaperPlanArtifact:
    plan_id: str
    source_run_id: str
    created_at: datetime
    symbol: str
    mode: str
    provider: str
    source_artifact_path: str
    thesis_recap: str
    constraints: list[str]
    risk_notes: list[str]
    invalidation_checks: list[str]
    paper_only_actions: list[str]
    verification_steps: list[str]
    warnings: list[str]
    artifact_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


def create_paper_plan(
    workspace_path: Path,
    run_id: str,
    *,
    event_logger: EventLogger | None = None,
    provider_name: str | None = None,
) -> PaperPlanArtifact:
    """Create a deterministic paper-only plan from an existing research artifact.

    This never touches broker submit paths.
    """
    safe_run_id = validate_run_id(run_id)

    # Resolve provider (only deterministic supported)
    _resolve_provider(provider_name)

    # Find and load source artifact
    source_path = find_research_artifact_by_run_id(workspace_path, safe_run_id)
    if source_path is None:
        raise ResearchSessionError("artifact_not_found")
    source = load_research_artifact(source_path, workspace_path)

    symbol = source.get("symbol", "UNKNOWN")
    plan_id = generate_run_id()
    created_at = datetime.now(UTC)
    warnings: list[str] = []

    # Build deterministic plan content
    thesis_recap = f"Recap of {symbol}: {source.get('thesis', 'No thesis available.')}"
    constraints = [
        "Paper-only plan.",
        "Does not authorize live trading.",
        "Does not create pending orders.",
    ]
    risk_notes = list(source.get("risks", []))
    if not risk_notes:
        risk_notes = ["No specific risks recorded in source artifact."]
    invalidation_checks = list(source.get("invalidation_conditions", []))
    if not invalidation_checks:
        invalidation_checks = ["No specific invalidation conditions recorded."]
    paper_only_actions = [
        "Review the source research artifact.",
        "Run a paper simulation or backtest before any approval workflow.",
        "Check risk limits before considering any separate approval workflow.",
    ]
    verification_steps = [
        "Review market data freshness.",
        "Compare plan assumptions with latest available data.",
        "Do not treat this plan as live-submit authorization.",
    ]

    plan = PaperPlanArtifact(
        plan_id=plan_id,
        source_run_id=safe_run_id,
        created_at=created_at,
        symbol=symbol,
        mode="paper",
        provider="deterministic",
        source_artifact_path=source.get("artifact_path", ""),
        thesis_recap=thesis_recap,
        constraints=constraints,
        risk_notes=risk_notes,
        invalidation_checks=invalidation_checks,
        paper_only_actions=paper_only_actions,
        verification_steps=verification_steps,
        warnings=warnings,
        artifact_path="",
        metadata={
            "provider_requested": provider_name or "deterministic",
            "source_provider": source.get("provider", "unknown"),
        },
    )

    # Persist plan artifact
    plan_dir = workspace_path / RESEARCH_DIR / symbol / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / f"{plan_id}.json"
    _write_plan_safe_json(plan_file, plan)

    plan = PaperPlanArtifact(
        plan_id=plan.plan_id,
        source_run_id=plan.source_run_id,
        created_at=plan.created_at,
        symbol=plan.symbol,
        mode=plan.mode,
        provider=plan.provider,
        source_artifact_path=plan.source_artifact_path,
        thesis_recap=plan.thesis_recap,
        constraints=plan.constraints,
        risk_notes=plan.risk_notes,
        invalidation_checks=plan.invalidation_checks,
        paper_only_actions=plan.paper_only_actions,
        verification_steps=plan.verification_steps,
        warnings=plan.warnings,
        artifact_path=plan_file.relative_to(workspace_path).as_posix(),
        metadata=plan.metadata,
    )

    # Log safe event
    if event_logger is not None:
        payload = {
            "plan_id": plan_id,
            "source_run_id": safe_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": "deterministic",
            "artifact_path": plan.artifact_path,
            "status": "created",
        }
        event_logger.write(
            "research_plan_created",
            run_id=plan_id,
            command="atlas research plan",
            mode="paper",
            payload=payload,
        )

    return plan


def _write_plan_safe_json(path: Path, plan: PaperPlanArtifact) -> None:
    data: dict[str, Any] = {
        "plan_id": plan.plan_id,
        "source_run_id": plan.source_run_id,
        "created_at": plan.created_at.isoformat(),
        "symbol": plan.symbol,
        "mode": plan.mode,
        "provider": plan.provider,
        "source_artifact_path": plan.source_artifact_path,
        "thesis_recap": plan.thesis_recap,
        "constraints": plan.constraints,
        "risk_notes": plan.risk_notes,
        "invalidation_checks": plan.invalidation_checks,
        "paper_only_actions": plan.paper_only_actions,
        "verification_steps": plan.verification_steps,
        "warnings": plan.warnings,
        "artifact_path": plan.artifact_path,
        "metadata": plan.metadata,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def find_plan_artifact_by_plan_id(
    workspace_path: Path, plan_id: str
) -> Path | None:
    """Find exactly one plan artifact by plan_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_plan_id = validate_run_id(plan_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        plans_dir = sym_dir / "plans"
        if not plans_dir.exists():
            continue
        candidate = plans_dir / f"{safe_plan_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_plan_id")
    return matches[0]


@dataclass(frozen=True)
class VerificationArtifact:
    verification_id: str
    source_plan_id: str
    source_run_id: str
    created_at: datetime
    symbol: str
    mode: str
    provider: str
    source_plan_path: str
    checks: list[dict[str, str]]
    passed_checks: int
    failed_checks: int
    warnings: list[str]
    recommendation: str
    artifact_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


_DANGEROUS_PHRASES = (
    "live submit authorized",
    "submit live order",
    "create pending order",
    "place order",
    "execute trade",
    "financial advice",
    "guaranteed profit",
    "risk-free",
    "safe live trading",
    "production-ready live trading",
)

_REQUIRED_PLAN_KEYS = (
    "plan_id",
    "source_run_id",
    "symbol",
    "mode",
    "provider",
    "thesis_recap",
    "constraints",
    "risk_notes",
    "invalidation_checks",
    "paper_only_actions",
    "verification_steps",
)


def _check_plan_schema_complete(plan: dict[str, Any]) -> dict[str, str]:
    missing = [k for k in _REQUIRED_PLAN_KEYS if k not in plan]
    if missing:
        return {"name": "plan_schema_complete", "status": "fail", "message": "Plan is missing required fields."}
    return {"name": "plan_schema_complete", "status": "pass", "message": "Plan schema is complete."}


def _check_paper_only_mode(plan: dict[str, Any]) -> dict[str, str]:
    if plan.get("mode") == "paper":
        return {"name": "paper_only_mode", "status": "pass", "message": "Mode is paper."}
    return {"name": "paper_only_mode", "status": "fail", "message": "Mode is not paper."}


def _check_no_live_authorization_language(plan: dict[str, Any]) -> dict[str, str]:
    text = json.dumps(plan, sort_keys=True).lower()
    for phrase in _DANGEROUS_PHRASES:
        idx = text.find(phrase.lower())
        if idx == -1:
            continue
        # Look for negative context immediately before the phrase
        window_start = max(0, idx - 40)
        context = text[window_start:idx]
        negative_indicators = ("not ", "does not ", "never ", "no ", "without ")
        if any(context.endswith(ind) or (" " + ind) in context for ind in negative_indicators):
            continue
        return {"name": "no_live_authorization_language", "status": "fail", "message": "Plan contains disallowed language."}
    return {"name": "no_live_authorization_language", "status": "pass", "message": "No disallowed language found."}


def _check_has_risk_notes(plan: dict[str, Any]) -> dict[str, str]:
    notes = plan.get("risk_notes", [])
    if isinstance(notes, list) and len(notes) > 0:
        return {"name": "has_risk_notes", "status": "pass", "message": "Risk notes are present."}
    return {"name": "has_risk_notes", "status": "fail", "message": "Risk notes are missing."}


def _check_has_invalidation_checks(plan: dict[str, Any]) -> dict[str, str]:
    checks = plan.get("invalidation_checks", [])
    if isinstance(checks, list) and len(checks) > 0:
        return {"name": "has_invalidation_checks", "status": "pass", "message": "Invalidation checks are present."}
    return {"name": "has_invalidation_checks", "status": "fail", "message": "Invalidation checks are missing."}


def _check_has_verification_steps(plan: dict[str, Any]) -> dict[str, str]:
    steps = plan.get("verification_steps", [])
    if isinstance(steps, list) and len(steps) > 0:
        return {"name": "has_verification_steps", "status": "pass", "message": "Verification steps are present."}
    return {"name": "has_verification_steps", "status": "fail", "message": "Verification steps are missing."}


def _check_has_paper_only_constraints(plan: dict[str, Any]) -> dict[str, str]:
    constraints = plan.get("constraints", [])
    if not isinstance(constraints, list):
        return {"name": "has_paper_only_constraints", "status": "fail", "message": "Constraints are missing."}
    text = " ".join(str(c) for c in constraints).lower()
    if "paper-only" in text or "paper only" in text or "does not authorize live trading" in text:
        return {"name": "has_paper_only_constraints", "status": "pass", "message": "Paper-only constraints are present."}
    return {"name": "has_paper_only_constraints", "status": "fail", "message": "Paper-only constraints are missing."}


def _check_source_path_contained(plan: dict[str, Any], workspace_path: Path) -> dict[str, str]:
    source_path = plan.get("source_artifact_path", "") or plan.get("artifact_path", "")
    if not source_path:
        return {"name": "source_path_contained", "status": "fail", "message": "Source path is missing."}
    # Workspace-relative is safe; absolute paths outside workspace are not
    if source_path.startswith("/"):
        try:
            p = Path(source_path).resolve()
            ws = workspace_path.resolve()
            p.relative_to(ws)
        except ValueError:
            return {"name": "source_path_contained", "status": "fail", "message": "Source path is outside workspace."}
    return {"name": "source_path_contained", "status": "pass", "message": "Source path is contained."}


def verify_paper_plan(
    workspace_path: Path,
    plan_id: str,
    *,
    event_logger: EventLogger | None = None,
    provider_name: str | None = None,
) -> VerificationArtifact:
    """Create a deterministic paper-only verification artifact from a plan.

    This never touches broker submit paths.
    """
    safe_plan_id = validate_run_id(plan_id)

    # Resolve provider (only deterministic supported)
    _resolve_provider(provider_name)

    # Find and load source plan
    plan_path = find_plan_artifact_by_plan_id(workspace_path, safe_plan_id)
    if plan_path is None:
        raise ResearchSessionError("plan_not_found")
    plan = load_research_artifact(plan_path, workspace_path)

    symbol = plan.get("symbol", "UNKNOWN")
    source_run_id = plan.get("source_run_id", "")
    verification_id = generate_run_id()
    created_at = datetime.now(UTC)
    warnings: list[str] = []

    # Run checks
    checks: list[dict[str, str]] = [
        _check_plan_schema_complete(plan),
        _check_paper_only_mode(plan),
        _check_no_live_authorization_language(plan),
        _check_has_risk_notes(plan),
        _check_has_invalidation_checks(plan),
        _check_has_verification_steps(plan),
        _check_has_paper_only_constraints(plan),
        _check_source_path_contained(plan, workspace_path),
    ]

    passed_checks = sum(1 for c in checks if c["status"] == "pass")
    failed_checks = sum(1 for c in checks if c["status"] == "fail")

    if failed_checks == 0:
        recommendation = "paper_review_ready"
    else:
        recommendation = "manual_review_required"

    verification = VerificationArtifact(
        verification_id=verification_id,
        source_plan_id=safe_plan_id,
        source_run_id=source_run_id,
        created_at=created_at,
        symbol=symbol,
        mode="paper",
        provider="deterministic",
        source_plan_path=plan_path.relative_to(workspace_path).as_posix(),
        checks=checks,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        warnings=warnings,
        recommendation=recommendation,
        artifact_path="",
        metadata={
            "provider_requested": provider_name or "deterministic",
            "source_provider": plan.get("provider", "unknown"),
        },
    )

    # Persist verification artifact
    verification_dir = workspace_path / RESEARCH_DIR / symbol / "verifications"
    verification_dir.mkdir(parents=True, exist_ok=True)
    verification_file = verification_dir / f"{verification_id}.json"
    _write_verification_safe_json(verification_file, verification)

    verification = VerificationArtifact(
        verification_id=verification.verification_id,
        source_plan_id=verification.source_plan_id,
        source_run_id=verification.source_run_id,
        created_at=verification.created_at,
        symbol=verification.symbol,
        mode=verification.mode,
        provider=verification.provider,
        source_plan_path=verification.source_plan_path,
        checks=verification.checks,
        passed_checks=verification.passed_checks,
        failed_checks=verification.failed_checks,
        warnings=verification.warnings,
        recommendation=verification.recommendation,
        artifact_path=verification_file.relative_to(workspace_path).as_posix(),
        metadata=verification.metadata,
    )

    # Log safe event
    if event_logger is not None:
        payload = {
            "verification_id": verification_id,
            "source_plan_id": safe_plan_id,
            "source_run_id": source_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": "deterministic",
            "recommendation": recommendation,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "artifact_path": verification.artifact_path,
            "status": "created",
        }
        event_logger.write(
            "research_verification_created",
            run_id=verification_id,
            command="atlas research verify",
            mode="paper",
            payload=payload,
        )

    return verification


def _write_verification_safe_json(path: Path, verification: VerificationArtifact) -> None:
    data: dict[str, Any] = {
        "verification_id": verification.verification_id,
        "source_plan_id": verification.source_plan_id,
        "source_run_id": verification.source_run_id,
        "created_at": verification.created_at.isoformat(),
        "symbol": verification.symbol,
        "mode": verification.mode,
        "provider": verification.provider,
        "source_plan_path": verification.source_plan_path,
        "checks": verification.checks,
        "passed_checks": verification.passed_checks,
        "failed_checks": verification.failed_checks,
        "warnings": verification.warnings,
        "recommendation": verification.recommendation,
        "artifact_path": verification.artifact_path,
        "metadata": verification.metadata,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_safe_json(path: Path, artifact: ResearchArtifact) -> None:
    data: dict[str, Any] = {
        "run_id": artifact.run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "summary": artifact.summary,
        "thesis": artifact.thesis,
        "market_context": artifact.market_context,
        "risks": artifact.risks,
        "invalidation_conditions": artifact.invalidation_conditions,
        "paper_only_plan": artifact.paper_only_plan,
        "memory_hits": artifact.memory_hits,
        "citations": list(artifact.citations),
        "warnings": artifact.warnings,
        "artifact_path": artifact.artifact_path,
        "metadata": artifact.metadata,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class EvaluationArtifact:
    evaluation_id: str
    source_plan_id: str
    source_run_id: str
    created_at: datetime
    symbol: str
    mode: str
    provider: str
    source_plan_path: str
    data_source: str
    data_summary: dict[str, Any]
    checks: list[dict[str, str]]
    metrics: dict[str, Any]
    warnings: list[str]
    recommendation: str
    artifact_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _load_csv_data(data_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Load a local CSV file safely. Returns (rows, columns).

    Raises ResearchSessionError on missing required columns or malformed data.
    """
    if not data_path.exists() or not data_path.is_file():
        raise ResearchSessionError("evaluation_data_invalid")

    import csv

    try:
        with data_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows: list[dict[str, str]] = list(reader)
    except Exception:
        raise ResearchSessionError("evaluation_data_invalid")

    if not rows:
        raise ResearchSessionError("evaluation_data_invalid")

    # Normalize column names (case-insensitive, strip whitespace)
    if reader.fieldnames is None:
        raise ResearchSessionError("evaluation_data_invalid")
    columns = [c.strip().lower() for c in reader.fieldnames]

    # Required: date or timestamp, close
    has_date = any(c in columns for c in ("date", "timestamp"))
    has_close = "close" in columns
    if not has_date or not has_close:
        raise ResearchSessionError("evaluation_data_invalid")

    return rows, columns


def _check_plan_loaded(plan: dict[str, Any]) -> dict[str, str]:
    if plan.get("plan_id"):
        return {"name": "plan_loaded", "status": "pass", "message": "Plan exists and parsed."}
    return {"name": "plan_loaded", "status": "fail", "message": "Plan not loaded."}


def _check_data_file_loaded(rows: list[dict[str, str]], columns: list[str]) -> dict[str, str]:
    if rows and columns:
        return {"name": "data_file_loaded", "status": "pass", "message": "Data CSV exists and parses."}
    return {"name": "data_file_loaded", "status": "fail", "message": "Data CSV could not be loaded."}


def _check_data_has_required_columns(columns: list[str]) -> dict[str, str]:
    has_date = any(c in columns for c in ("date", "timestamp"))
    has_close = "close" in columns
    if has_date and has_close:
        return {"name": "data_has_required_columns", "status": "pass", "message": "Required columns present."}
    return {"name": "data_has_required_columns", "status": "fail", "message": "Missing required columns."}


def _check_data_has_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    if len(rows) > 0:
        return {"name": "data_has_rows", "status": "pass", "message": "Data has at least one row."}
    return {"name": "data_has_rows", "status": "fail", "message": "Data has no rows."}


def _check_data_symbol_context(rows: list[dict[str, str]], columns: list[str], symbol: str) -> dict[str, str]:
    if "symbol" not in columns:
        return {"name": "data_symbol_context", "status": "pass", "message": "No symbol column in data; skipping symbol match."}
    sym_values = set(r.get("symbol", "").strip().upper() for r in rows if r.get("symbol", "").strip())
    if not sym_values:
        return {"name": "data_symbol_context", "status": "pass", "message": "No symbol values in data; skipping symbol match."}
    if symbol.upper() in sym_values:
        return {"name": "data_symbol_context", "status": "pass", "message": "Data symbol matches plan symbol."}
    return {"name": "data_symbol_context", "status": "warn", "message": "Data symbol does not match plan symbol."}


def _check_plan_has_verification_steps(plan: dict[str, Any]) -> dict[str, str]:
    steps = plan.get("verification_steps", [])
    if isinstance(steps, list) and len(steps) > 0:
        return {"name": "plan_has_verification_steps", "status": "pass", "message": "Verification steps are present."}
    return {"name": "plan_has_verification_steps", "status": "fail", "message": "Verification steps are missing."}


def _check_plan_has_invalidation_checks(plan: dict[str, Any]) -> dict[str, str]:
    checks = plan.get("invalidation_checks", [])
    if isinstance(checks, list) and len(checks) > 0:
        return {"name": "plan_has_invalidation_checks", "status": "pass", "message": "Invalidation checks are present."}
    return {"name": "plan_has_invalidation_checks", "status": "fail", "message": "Invalidation checks are missing."}


def _check_no_live_authorization_language_eval(plan: dict[str, Any]) -> dict[str, str]:
    text = json.dumps(plan, sort_keys=True).lower()
    for phrase in _DANGEROUS_PHRASES:
        idx = text.find(phrase.lower())
        if idx == -1:
            continue
        window_start = max(0, idx - 40)
        context = text[window_start:idx]
        negative_indicators = ("not ", "does not ", "never ", "no ", "without ")
        if any(context.endswith(ind) or (" " + ind) in context for ind in negative_indicators):
            continue
        return {"name": "no_live_authorization_language", "status": "fail", "message": "Plan contains disallowed language."}
    return {"name": "no_live_authorization_language", "status": "pass", "message": "No disallowed language found."}


def _compute_data_metrics(rows: list[dict[str, str]], columns: list[str]) -> dict[str, Any]:
    """Compute safe, deterministic metrics from CSV rows."""
    metrics: dict[str, Any] = {"row_count": len(rows)}

    # Find close column
    close_col = None
    for c in columns:
        if c == "close":
            close_col = c
            break

    if close_col:
        close_values: list[float] = []
        for r in rows:
            try:
                v = float(r.get(close_col, "").strip())
                close_values.append(v)
            except (ValueError, TypeError):
                continue
        if close_values:
            metrics["latest_close"] = close_values[-1]
            metrics["min_close"] = min(close_values)
            metrics["max_close"] = max(close_values)

    # Find date/timestamp column
    date_col = None
    for c in columns:
        if c in ("date", "timestamp"):
            date_col = c
            break

    if date_col:
        first_val = rows[0].get(date_col, "")
        last_val = rows[-1].get(date_col, "")
        if first_val:
            metrics["first_date"] = str(first_val).strip()
        if last_val:
            metrics["last_date"] = str(last_val).strip()

    return metrics


def evaluate_paper_plan(
    workspace_path: Path,
    plan_id: str,
    data_path: Path,
    *,
    event_logger: EventLogger | None = None,
    provider_name: str | None = None,
) -> EvaluationArtifact:
    """Create a deterministic paper-only evaluation artifact from a plan and local data.

    This never touches broker submit paths.
    """
    safe_plan_id = validate_run_id(plan_id)

    # Resolve provider (only deterministic supported)
    _resolve_provider(provider_name)

    # Find and load source plan
    plan_path = find_plan_artifact_by_plan_id(workspace_path, safe_plan_id)
    if plan_path is None:
        raise ResearchSessionError("plan_not_found")
    plan = load_research_artifact(plan_path, workspace_path)

    symbol = plan.get("symbol", "UNKNOWN")
    source_run_id = plan.get("source_run_id", "")
    evaluation_id = generate_run_id()
    created_at = datetime.now(UTC)
    warnings: list[str] = []

    # Load local data
    rows, columns = _load_csv_data(data_path)

    # Run checks
    checks: list[dict[str, str]] = [
        _check_plan_loaded(plan),
        _check_paper_only_mode(plan),
        _check_data_file_loaded(rows, columns),
        _check_data_has_required_columns(columns),
        _check_data_has_rows(rows),
        _check_data_symbol_context(rows, columns, symbol),
        _check_plan_has_verification_steps(plan),
        _check_plan_has_invalidation_checks(plan),
        _check_no_live_authorization_language_eval(plan),
    ]

    passed_checks = sum(1 for c in checks if c["status"] == "pass")
    failed_checks = sum(1 for c in checks if c["status"] == "fail")

    if failed_checks == 0:
        recommendation = "paper_evaluation_ready"
    else:
        recommendation = "manual_review_required"

    metrics = _compute_data_metrics(rows, columns) if rows else {"row_count": 0}

    # Data source: workspace-relative if inside workspace, else filename only
    try:
        data_source_rel = data_path.relative_to(workspace_path).as_posix()
    except ValueError:
        data_source_rel = data_path.name

    evaluation = EvaluationArtifact(
        evaluation_id=evaluation_id,
        source_plan_id=safe_plan_id,
        source_run_id=source_run_id,
        created_at=created_at,
        symbol=symbol,
        mode="paper",
        provider="deterministic",
        source_plan_path=plan_path.relative_to(workspace_path).as_posix(),
        data_source=data_source_rel,
        data_summary={"row_count": metrics.get("row_count", 0)},
        checks=checks,
        metrics=metrics,
        warnings=warnings,
        recommendation=recommendation,
        artifact_path="",
        metadata={
            "provider_requested": provider_name or "deterministic",
            "source_provider": plan.get("provider", "unknown"),
        },
    )

    # Persist evaluation artifact
    evaluation_dir = workspace_path / RESEARCH_DIR / symbol / "evaluations"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    evaluation_file = evaluation_dir / f"{evaluation_id}.json"
    _write_evaluation_safe_json(evaluation_file, evaluation)

    evaluation = EvaluationArtifact(
        evaluation_id=evaluation.evaluation_id,
        source_plan_id=evaluation.source_plan_id,
        source_run_id=evaluation.source_run_id,
        created_at=evaluation.created_at,
        symbol=evaluation.symbol,
        mode=evaluation.mode,
        provider=evaluation.provider,
        source_plan_path=evaluation.source_plan_path,
        data_source=evaluation.data_source,
        data_summary=evaluation.data_summary,
        checks=evaluation.checks,
        metrics=evaluation.metrics,
        warnings=evaluation.warnings,
        recommendation=evaluation.recommendation,
        artifact_path=evaluation_file.relative_to(workspace_path).as_posix(),
        metadata=evaluation.metadata,
    )

    # Log safe event
    if event_logger is not None:
        payload = {
            "evaluation_id": evaluation_id,
            "source_plan_id": safe_plan_id,
            "source_run_id": source_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": "deterministic",
            "recommendation": recommendation,
            "artifact_path": evaluation.artifact_path,
            "status": "created",
            "row_count": metrics.get("row_count", 0),
        }
        event_logger.write(
            "research_evaluation_created",
            run_id=evaluation_id,
            command="atlas research evaluate",
            mode="paper",
            payload=payload,
        )

    return evaluation


def _write_evaluation_safe_json(path: Path, evaluation: EvaluationArtifact) -> None:
    data: dict[str, Any] = {
        "evaluation_id": evaluation.evaluation_id,
        "source_plan_id": evaluation.source_plan_id,
        "source_run_id": evaluation.source_run_id,
        "created_at": evaluation.created_at.isoformat(),
        "symbol": evaluation.symbol,
        "mode": evaluation.mode,
        "provider": evaluation.provider,
        "source_plan_path": evaluation.source_plan_path,
        "data_source": evaluation.data_source,
        "data_summary": evaluation.data_summary,
        "checks": evaluation.checks,
        "metrics": evaluation.metrics,
        "warnings": evaluation.warnings,
        "recommendation": evaluation.recommendation,
        "artifact_path": evaluation.artifact_path,
        "metadata": evaluation.metadata,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
