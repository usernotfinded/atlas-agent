# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/session.py
# PURPOSE: The research session lifecycle — plan, prompt, run, verify, evaluate, and
#          the artifacts each step seals. The spine the rest of research/ hangs off.
# DEPS:    research.artifact_store, research.command_specs, research.errors
#
# WARNING: At ~6.7k lines this is by far the largest file in the project, and it is
#          past the point where section banners can rescue it. The convention's own
#          rule applies: "if a file needs more than ~5 banners to be navigable, the
#          file is too big". This is the primary decomposition candidate — the
#          banners below are a map of a building that should be several buildings.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas_agent.events.log import EventLogger, generate_run_id
from atlas_agent.research.sandbox_contracts import FORBIDDEN_FRAGMENTS, artifact_sha256
from atlas_agent.research.providers import (
    ResearchContext,
    UnsupportedResearchProviderError,
    resolve_research_provider,
)

if TYPE_CHECKING:
    from atlas_agent.learning.memory_index import MemoryIndexResult
    from atlas_agent.research.research_report import ResearchReport


RESEARCH_DIR = Path(".atlas") / "research"

SUPPORTED_RESEARCH_PROVIDERS = {"deterministic"}

RESEARCH_ARTIFACT_SCHEMA_VERSION = "1"


class ResearchSessionError(RuntimeError):
    pass


class InvalidResearchSymbolError(ResearchSessionError):
    pass


class UnsupportedArtifactSchemaError(ResearchSessionError):
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
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION


class DeterministicResearchProvider:
    """A deterministic, local, network-free research provider."""

    @property
    def name(self) -> str:
        return "deterministic"

    def generate_research(self, symbol: str, context: ResearchContext) -> "ResearchProviderResult":
        from atlas_agent.research.providers import ResearchProviderResult

        return ResearchProviderResult(
            provider="deterministic",
            summary=f"Deterministic market context for {symbol.upper()}. No external data queried.",
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
            metadata={"source": "deterministic"},
        )

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
        raise InvalidResearchSymbolError("Invalid research symbol.")
    if "/" in symbol or "\\" in symbol or symbol.startswith(".") or ".." in symbol:
        raise InvalidResearchSymbolError("Invalid research symbol.")
    sanitized = ""
    for ch in symbol:
        if ch.isalnum() or ch in "-_":
            sanitized += ch
        elif ch == "." and sanitized:
            sanitized += ch
    if not sanitized:
        raise InvalidResearchSymbolError("Invalid research symbol.")
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
    return resolve_research_provider(provider_name)


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
    result = research_provider.generate_research(
        safe_symbol,
        ResearchContext(symbol=safe_symbol, mode="paper"),
    )

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
        provider=result.provider,
        summary=result.summary,
        thesis=result.thesis,
        market_context=result.market_context,
        risks=result.risks,
        invalidation_conditions=result.invalidation_conditions,
        paper_only_plan=result.paper_only_plan,
        citations=tuple(result.citations),
        memory_hits=memory_hits,
        warnings=warnings + result.warnings,
        run_id=run_id,
        created_at=created_at,
        artifact_path="",
        metadata={"provider_requested": provider_name or "deterministic", **result.metadata},
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
            "provider": result.provider,
            "artifact_path": artifact.artifact_path,
            "status": "created",
            "schema_version": artifact.schema_version,
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
    from atlas_agent.research.artifact_store import ArtifactKind, ResearchArtifactStore

    store = ResearchArtifactStore(workspace_path)
    kind = ArtifactKind(name="research", id_field="run_id")
    entries = store.list_entries(kind, symbol=symbol)

    items: list[dict[str, Any]] = []
    for entry in entries:
        if entry.is_malformed:
            items.append(
                {
                    "run_id": entry.path.stem,
                    "symbol": entry.symbol,
                    "created_at": "",
                    "artifact_path": entry.path.relative_to(workspace_path).as_posix(),
                    "provider": "unknown",
                    "warnings_count": 1,
                    "_malformed": True,
                }
            )
            continue
        data = entry.data
        assert data is not None
        items.append(
            {
                "run_id": data.get("run_id", entry.path.stem),
                "symbol": data.get("symbol", entry.symbol),
                "created_at": data.get("created_at", ""),
                "artifact_path": entry.path.relative_to(workspace_path).as_posix(),
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
    from atlas_agent.research.artifact_store import ArtifactKind, ResearchArtifactStore

    store = ResearchArtifactStore(workspace_path)
    kind = ArtifactKind(name="plan", id_field="plan_id", subdir="plans")
    entries = store.list_entries(kind, symbol=symbol)

    items: list[dict[str, Any]] = []
    for entry in entries:
        if entry.is_malformed:
            items.append(
                {
                    "plan_id": entry.path.stem,
                    "symbol": entry.symbol,
                    "created_at": "",
                    "artifact_path": entry.path.relative_to(workspace_path).as_posix(),
                    "provider": "unknown",
                    "warnings_count": 1,
                    "_malformed": True,
                }
            )
            continue
        data = entry.data
        assert data is not None
        items.append(
            {
                "plan_id": data.get("plan_id", entry.path.stem),
                "source_run_id": data.get("source_run_id", ""),
                "symbol": data.get("symbol", entry.symbol),
                "created_at": data.get("created_at", ""),
                "artifact_path": entry.path.relative_to(workspace_path).as_posix(),
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


def _check_schema_version(data: dict[str, Any], artifact_type: str) -> None:
    """Fail closed if schema_version is present and unsupported."""
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError(
            f"unsupported_{artifact_type}_artifact_schema"
        )


def load_research_artifact(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a research artifact JSON safely.

    Returns a dict with a computed workspace-relative artifact_path.
    """
    from atlas_agent.research.artifact_store import ResearchArtifactStore

    store = ResearchArtifactStore(workspace_path)
    return store.load_artifact(path, artifact_type="research")


def find_research_artifact_by_run_id(
    workspace_path: Path, run_id: str
) -> Path | None:
    """Find exactly one artifact by run_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    from atlas_agent.research.artifact_store import ArtifactKind, ResearchArtifactStore

    store = ResearchArtifactStore(workspace_path)
    kind = ArtifactKind(name="research", id_field="run_id")
    return store.find_by_id(kind, run_id)


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
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION


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
            "schema_version": plan.schema_version,
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
        "schema_version": plan.schema_version,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def find_plan_artifact_by_plan_id(
    workspace_path: Path, plan_id: str
) -> Path | None:
    """Find exactly one plan artifact by plan_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    from atlas_agent.research.artifact_store import ArtifactKind, ResearchArtifactStore

    store = ResearchArtifactStore(workspace_path)
    kind = ArtifactKind(name="plan", id_field="plan_id", subdir="plans")
    return store.find_by_id(kind, plan_id)


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
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION


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
            "schema_version": verification.schema_version,
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
        "schema_version": verification.schema_version,
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
        "schema_version": artifact.schema_version,
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
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION


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
            "schema_version": evaluation.schema_version,
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
        "schema_version": evaluation.schema_version,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def check_research_artifacts(
    workspace_path: Path,
    symbol_filter: str | None = None,
) -> dict[str, Any]:
    """Read-only health check of local research artifacts.

    Returns counts, issues, and warnings. Never modifies artifacts.
    """
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    counts = {"research": 0, "plans": 0, "verifications": 0, "evaluations": 0, "prompts": 0, "provider_responses": 0, "response_reviews": 0, "dossiers": 0, "sandbox_requests": 0, "provider_call_plans": 0, "provider_execution_dry_runs": 0, "provider_execution_states": 0, "provider_execution_audit_packets": 0, "provider_execution_readiness_reports": 0, "provider_preflight_freezes": 0, "provider_opt_in_policies": 0, "provider_credential_boundaries": 0, "provider_outbound_payload_previews": 0, "provider_response_intake_policies": 0, "provider_request_response_pairings": 0, "provider_response_schema_contracts": 0, "provider_response_review_results": 0, "provider_execution_unlock_states": 0, "provider_adapter_interface_contracts": 0, "provider_mock_response_simulations": 0, "provider_mock_response_import_candidates": 0, "provider_mock_response_review_sandboxes": 0, "provider_mock_response_trust_decision_blockers": 0, "provider_mock_response_final_safety_seals": 0, "release_candidate_readiness_reports": 0}

    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return {
            "ok": True,
            "status": "research_artifacts_checked",
            "counts": counts,
            "issues": issues,
            "warnings": warnings,
        }

    search_symbols: list[Path] = []
    if symbol_filter is not None:
        safe = sanitize_symbol(symbol_filter)
        sym_dir = research_dir / safe
        if sym_dir.exists():
            search_symbols.append(sym_dir)
    else:
        search_symbols = [d for d in research_dir.iterdir() if d.is_dir()]

    # Track IDs per type for duplicate detection
    run_ids: dict[str, list[str]] = {}
    plan_ids: dict[str, list[str]] = {}
    verification_ids: dict[str, list[str]] = {}
    evaluation_ids: dict[str, list[str]] = {}
    prompt_ids: dict[str, list[str]] = {}
    provider_response_ids: dict[str, list[str]] = {}
    response_review_ids: dict[str, list[str]] = {}
    dossier_ids: dict[str, list[str]] = {}
    sandbox_request_ids: dict[str, list[str]] = {}
    provider_call_plan_ids: dict[str, list[str]] = {}
    provider_execution_dry_run_ids: dict[str, list[str]] = {}
    provider_execution_state_ids: dict[str, list[str]] = {}
    provider_execution_audit_packet_ids: dict[str, list[str]] = {}
    provider_execution_readiness_report_ids: dict[str, list[str]] = {}
    release_candidate_readiness_report_ids: dict[str, list[str]] = {}
    provider_preflight_freeze_ids: dict[str, list[str]] = {}
    provider_opt_in_policy_ids: dict[str, list[str]] = {}
    provider_credential_boundary_ids: dict[str, list[str]] = {}

    provider_call_plan_data: list[dict[str, Any]] = []
    provider_execution_dry_run_data: list[dict[str, Any]] = []
    provider_execution_state_data: list[dict[str, Any]] = []
    provider_execution_audit_packet_data: list[dict[str, Any]] = []
    provider_execution_readiness_report_data: list[dict[str, Any]] = []
    release_candidate_readiness_report_data: list[dict[str, Any]] = []
    provider_preflight_freeze_data: list[dict[str, Any]] = []
    provider_opt_in_policy_data: list[dict[str, Any]] = []
    provider_credential_boundary_data: list[dict[str, Any]] = []
    provider_outbound_payload_preview_ids: dict[str, list[str]] = {}
    provider_outbound_payload_preview_data: list[dict[str, Any]] = []
    provider_response_intake_policy_ids: dict[str, list[str]] = {}
    provider_response_intake_policy_data: list[dict[str, Any]] = []
    provider_request_response_pairing_ids: dict[str, list[str]] = {}
    provider_request_response_pairing_data: list[dict[str, Any]] = []
    provider_response_schema_contract_ids: dict[str, list[str]] = {}
    provider_response_schema_contract_data: list[dict[str, Any]] = []
    provider_response_review_result_ids: dict[str, list[str]] = {}
    provider_response_review_result_data: list[dict[str, Any]] = []
    provider_execution_unlock_state_ids: dict[str, list[str]] = {}
    provider_execution_unlock_state_data: list[dict[str, Any]] = []
    provider_adapter_interface_contract_ids: dict[str, list[str]] = {}
    provider_adapter_interface_contract_data: list[dict[str, Any]] = []
    provider_mock_response_simulation_ids: dict[str, list[str]] = {}
    provider_mock_response_simulation_data: list[dict[str, Any]] = []
    provider_mock_response_import_candidate_ids: dict[str, list[str]] = {}
    provider_mock_response_import_candidate_data: list[dict[str, Any]] = []
    provider_mock_response_review_sandbox_ids: dict[str, list[str]] = {}
    provider_mock_response_review_sandbox_data: list[dict[str, Any]] = []
    provider_mock_response_trust_decision_blocker_ids: dict[str, list[str]] = {}
    provider_mock_response_trust_decision_blocker_data: list[dict[str, Any]] = []
    provider_mock_response_final_safety_seal_ids: dict[str, list[str]] = {}
    provider_mock_response_final_safety_seal_data: list[dict[str, Any]] = []
    sandbox_request_data_by_id: dict[str, dict[str, Any]] = {}

    def _rel(path: Path) -> str:
        try:
            return path.relative_to(workspace_path).as_posix()
        except ValueError:
            return path.name

    def _inspect_file(path: Path, expected_type: str, expected_symbol: str) -> None:
        rel = _rel(path)
        # unsafe path check
        if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
            issues.append({"code": "unsafe_path", "path": rel, "severity": "error"})
            return
        # malformed JSON
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            issues.append({"code": "malformed_json", "path": rel, "severity": "error"})
            return
        # unsupported schema version
        sv = data.get("schema_version")
        if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
            issues.append({"code": "unsupported_schema_version", "path": rel, "severity": "error"})
            return
        # legacy schema version
        if sv is None:
            warnings.append({"code": "legacy_schema_version", "path": rel, "severity": "warning"})
        # missing required fields
        id_field = {
            "research": "run_id",
            "plan": "plan_id",
            "verification": "verification_id",
            "evaluation": "evaluation_id",
            "prompt": "prompt_packet_id",
            "provider_response": "provider_response_id",
            "response_review": "response_review_id",
            "dossier": "dossier_id",
            "sandbox_request": "sandbox_request_id",
            "provider_call_plan": "provider_call_plan_id",
            "provider_execution_dry_run": "provider_execution_dry_run_id",
            "provider_execution_state": "provider_execution_state_id",
            "provider_execution_audit_packet": "provider_execution_audit_packet_id",
            "provider_execution_readiness_report": "provider_execution_readiness_report_id",
            "provider_preflight_freeze": "provider_preflight_freeze_id",
            "provider_opt_in_policy": "provider_opt_in_policy_id",
            "provider_credential_boundary": "provider_credential_boundary_id",
            "provider_outbound_payload_preview": "provider_outbound_payload_preview_id",
            "provider_response_intake_policy": "provider_response_intake_policy_id",
            "provider_request_response_pairing": "provider_request_response_pairing_id",
            "provider_response_review_result": "provider_response_review_result_id",
            "provider_execution_unlock_state": "provider_execution_unlock_state_id",
            "provider_adapter_interface_contract": "provider_adapter_interface_contract_id",
            "provider_mock_response_simulation": "provider_mock_response_simulation_id",
            "provider_mock_response_import_candidate": "provider_mock_response_import_candidate_id",
            "provider_mock_response_review_sandbox": "provider_mock_response_review_sandbox_id",
        }.get(expected_type)
        if id_field and id_field not in data:
            issues.append({"code": "missing_required_id", "path": rel, "severity": "error"})
            return
        # symbol mismatch
        artifact_symbol = data.get("symbol", "")
        if artifact_symbol and artifact_symbol != expected_symbol:
            warnings.append(
                {
                    "code": "symbol_mismatch",
                    "path": rel,
                    "severity": "warning",
                }
            )
        # unexpected location
        if expected_type == "dossier" and "dossiers" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "plan" and "plans" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "verification" and "verifications" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "evaluation" and "evaluations" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "prompt" and "prompts" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_response" and "provider_responses" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "sandbox_request" and "sandbox_requests" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_call_plan" and "provider_call_plans" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_execution_dry_run" and "provider_execution_dry_runs" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_execution_state" and "provider_execution_states" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_execution_audit_packet" and "provider_execution_audit_packets" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_execution_readiness_report" and "provider_execution_readiness_reports" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_preflight_freeze" and "provider_preflight_freezes" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_opt_in_policy" and "provider_opt_in_policies" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_credential_boundary" and "provider_credential_boundaries" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_outbound_payload_preview" and "provider_outbound_payload_previews" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_response_intake_policy" and "provider_response_intake_policies" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_request_response_pairing" and "provider_request_response_pairings" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_response_review_result" and "provider_response_review_results" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_execution_unlock_state" and "provider_execution_unlock_states" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_adapter_interface_contract" and "provider_adapter_interface_contracts" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_mock_response_simulation" and "provider_mock_response_simulations" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        # minimal required fields
        if expected_type == "research":
            for f in ("mode", "provider", "artifact_path"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type in ("plan",):
            for f in ("source_run_id", "symbol", "mode", "provider"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "verification":
            for f in ("source_plan_id", "symbol", "mode", "provider", "recommendation"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "evaluation":
            for f in ("source_plan_id", "symbol", "mode", "provider", "recommendation"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "prompt":
            for f in ("prompt_packet_id", "source_run_id", "symbol", "mode", "provider"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_response":
            for f in ("provider_response_id", "source_prompt_packet_id", "source_run_id", "symbol", "mode", "provider", "recommendation"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "response_review":
            for f in ("response_review_id", "source_provider_response_id", "source_prompt_packet_id", "source_run_id", "symbol", "mode", "provider", "recommendation"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "dossier":
            for f in ("dossier_id", "source_run_id", "symbol", "mode", "provider", "recommendation"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
        elif expected_type == "release_candidate_readiness_report":
            for f in ("release_candidate_readiness_report_id", "symbol", "version", "readiness_status", "readiness_score"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.release_candidate_readiness import safe_validate_release_candidate_readiness_data
            _cleaned, error = safe_validate_release_candidate_readiness_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "sandbox_request":
            for f in ("sandbox_request_id", "prompt_packet_id", "source_run_id", "symbol", "mode", "provider"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Hash validation
            stored_hash = data.get("content_hash", "")
            if stored_hash:
                computed = artifact_sha256(data)
                if computed != stored_hash:
                    issues.append({"code": "hash_mismatch", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_call_plan":
            for f in ("provider_call_plan_id", "source_sandbox_request_id", "symbol", "provider_id", "model_id"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Use provider_call_plan safe validation
            from atlas_agent.research.provider_call_plan import (
                safe_validate_provider_call_plan_data,
            )
            _cleaned, error = safe_validate_provider_call_plan_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_execution_dry_run":
            for f in ("provider_execution_dry_run_id", "source_provider_call_plan_id", "symbol", "provider_id", "model_id"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Use provider_execution_dry_run safe validation
            from atlas_agent.research.provider_execution_dry_run import (
                safe_validate_provider_execution_dry_run_data,
            )
            _cleaned, error = safe_validate_provider_execution_dry_run_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_execution_state":
            for f in ("provider_execution_state_id", "source_provider_execution_dry_run_id", "symbol", "provider_id", "model_id", "state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Use provider_execution_state safe validation
            from atlas_agent.research.provider_execution_state import (
                safe_validate_provider_execution_state_data,
            )
            _cleaned, error = safe_validate_provider_execution_state_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_execution_audit_packet":
            for f in ("provider_execution_audit_packet_id", "source_provider_execution_state_id", "symbol", "provider_id", "model_id", "audit_status", "execution_status"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Use provider_execution_audit_packet safe validation
            from atlas_agent.research.provider_execution_audit_packet import (
                safe_validate_provider_execution_audit_packet_data,
            )
            _cleaned, error = safe_validate_provider_execution_audit_packet_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_execution_readiness_report":
            for f in ("provider_execution_readiness_report_id", "source_provider_execution_audit_packet_id", "symbol", "provider_id", "model_id", "readiness_status", "readiness_score", "chain_health"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Use provider_execution_readiness_report safe validation
            from atlas_agent.research.provider_execution_readiness_report import (
                safe_validate_provider_execution_readiness_report_data,
            )
            _cleaned, error = safe_validate_provider_execution_readiness_report_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_preflight_freeze":
            for f in ("provider_preflight_freeze_id", "source_provider_execution_readiness_report_id", "symbol", "provider_id", "model_id", "freeze_status", "freeze_recommendation", "readiness_score", "chain_health"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            # Use provider_preflight_freeze safe validation
            from atlas_agent.research.provider_preflight_freeze import (
                safe_validate_provider_preflight_freeze_data,
            )
            _cleaned, error = safe_validate_provider_preflight_freeze_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_opt_in_policy":
            for f in ("provider_opt_in_policy_id", "source_provider_preflight_freeze_id", "symbol", "provider_id", "model_id", "policy_status", "policy_scope", "opt_in_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_opt_in_policy import (
                safe_validate_provider_opt_in_policy_data,
            )
            _cleaned, error = safe_validate_provider_opt_in_policy_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_credential_boundary":
            for f in ("provider_credential_boundary_id", "source_provider_opt_in_policy_id", "symbol", "provider_id", "model_id", "credential_boundary_status", "credential_boundary_scope", "credential_loading_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_credential_boundary import (
                safe_validate_provider_credential_boundary_data,
            )
            _cleaned, error = safe_validate_provider_credential_boundary_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_outbound_payload_preview":
            for f in ("provider_outbound_payload_preview_id", "source_provider_credential_boundary_id", "symbol", "provider_id", "model_id", "payload_preview_status", "payload_preview_scope"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_outbound_payload_preview import (
                safe_validate_provider_outbound_payload_preview_data,
            )
            _cleaned, error = safe_validate_provider_outbound_payload_preview_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_response_intake_policy":
            for f in ("provider_response_intake_policy_id", "source_provider_outbound_payload_preview_id", "symbol", "provider_id", "model_id", "response_intake_policy_status", "response_intake_policy_scope"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_response_intake_policy import (
                safe_validate_provider_response_intake_policy_data,
            )
            _cleaned, error = safe_validate_provider_response_intake_policy_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_request_response_pairing":
            for f in ("provider_request_response_pairing_id", "source_provider_response_intake_policy_id", "source_provider_outbound_payload_preview_id", "symbol", "provider_id", "model_id", "pairing_status", "pairing_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_request_response_pairing import (
                safe_validate_provider_request_response_pairing_data,
            )
            _cleaned, error = safe_validate_provider_request_response_pairing_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_response_schema_contract":
            for f in ("provider_response_schema_contract_id", "source_provider_request_response_pairing_id", "source_provider_response_intake_policy_id", "source_provider_outbound_payload_preview_id", "symbol", "provider_id", "model_id", "response_schema_status", "response_schema_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_response_schema_contract import (
                safe_validate_provider_response_schema_contract_data,
            )
            _cleaned, error = safe_validate_provider_response_schema_contract_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            # Forbidden fragments in raw file
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_response_review_result":
            for f in ("provider_response_review_result_id", "source_provider_response_schema_contract_id", "source_provider_request_response_pairing_id", "source_provider_response_intake_policy_id", "source_provider_outbound_payload_preview_id", "symbol", "provider_id", "model_id", "review_result_status", "review_result_state", "review_decision"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_response_review_result import (
                safe_validate_provider_response_review_result_data,
            )
            _cleaned, error = safe_validate_provider_response_review_result_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
        elif expected_type == "provider_execution_unlock_state":
            for f in ("provider_execution_unlock_state_id", "source_provider_response_review_result_id", "source_provider_response_schema_contract_id", "source_provider_request_response_pairing_id", "source_provider_response_intake_policy_id", "source_provider_outbound_payload_preview_id", "symbol", "provider_id", "model_id", "unlock_state_status", "unlock_state", "current_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_execution_unlock_state import (
                safe_validate_provider_execution_unlock_state_data,
            )
            _cleaned, error = safe_validate_provider_execution_unlock_state_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
            # Check impossible booleans for unlock state
            impossible_booleans = [
                "manual_unlock_requested", "manual_unlock_granted", "manual_unlock_revoked",
                "provider_execution_unlocked", "provider_enabled", "network_enabled",
                "credentials_loaded", "credential_value_present", "credential_lookup_attempted",
                "env_read_attempted", "dotenv_loaded", "provider_adapter_present",
                "provider_adapter_enabled", "provider_call_allowed", "actual_provider_call_made",
                "outbound_request_sent", "future_provider_execution_possible",
                "future_response_artifact_present", "provider_response_received",
                "provider_response_trusted", "provider_response_imported",
                "provider_response_reviewed", "review_result_present", "manual_review_gate_open",
                "trust_upgrade_performed", "provider_response_can_create_orders",
                "provider_response_can_approve_orders", "provider_response_can_call_broker",
                "trading_signal_generated", "approval_created", "pending_order_created", "broker_touched",
            ]
            for b in impossible_booleans:
                if data.get(b) is True:
                    issues.append({"code": "provider_execution_unlock_state_impossible_boolean", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_adapter_interface_contract":
            for f in ("provider_adapter_interface_contract_id", "source_provider_execution_unlock_state_id", "source_provider_response_review_result_id", "source_provider_response_schema_contract_id", "source_provider_request_response_pairing_id", "source_provider_response_intake_policy_id", "source_provider_outbound_payload_preview_id", "symbol", "provider_id", "model_id", "adapter_contract_status", "adapter_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_adapter_interface_contract import (
                safe_validate_provider_adapter_interface_contract_data,
            )
            _cleaned, error = safe_validate_provider_adapter_interface_contract_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
            # Check impossible booleans for adapter interface contract
            impossible_booleans = [
                "adapter_present", "adapter_enabled", "real_provider_adapter_implemented",
                "provider_sdk_imported", "http_client_imported", "network_enabled",
                "network_call_attempted", "credentials_loaded", "credential_value_present",
                "credential_lookup_attempted", "env_read_attempted", "dotenv_loaded",
                "provider_execution_unlocked", "manual_unlock_granted", "provider_call_allowed",
                "actual_provider_call_made", "outbound_request_sent", "provider_response_received",
                "provider_response_trusted", "trust_upgrade_performed",
                "trading_signal_generated", "approval_created", "pending_order_created", "broker_touched",
            ]
            for b in impossible_booleans:
                if data.get(b) is True:
                    issues.append({"code": "provider_adapter_interface_contract_impossible_boolean", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_mock_response_simulation":
            for f in ("provider_mock_response_simulation_id", "source_provider_adapter_interface_contract_id", "symbol", "provider_id", "model_id", "mock_simulation_status", "mock_simulation_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_mock_response_simulation import (
                safe_validate_provider_mock_response_simulation_data,
            )
            _cleaned, error = safe_validate_provider_mock_response_simulation_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
            # Check impossible booleans for mock response simulation
            impossible_booleans = [
                "real_provider_adapter_used", "real_provider_request_sent", "real_provider_response_received",
                "provider_response_received", "provider_response_trusted", "mock_response_trusted",
                "network_enabled", "network_call_attempted", "credentials_loaded", "credential_value_present",
                "credential_lookup_attempted", "env_read_attempted", "dotenv_loaded",
                "provider_execution_unlocked", "manual_unlock_granted", "provider_call_allowed",
                "actual_provider_call_made", "outbound_request_sent", "trust_upgrade_performed",
                "trading_signal_generated", "approval_created", "pending_order_created", "broker_touched",
            ]
            for b in impossible_booleans:
                if data.get(b) is True:
                    issues.append({"code": "provider_mock_response_simulation_impossible_boolean", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_mock_response_import_candidate":
            for f in ("provider_mock_response_import_candidate_id", "source_provider_mock_response_simulation_id", "symbol", "provider_id", "model_id", "mock_import_candidate_status", "mock_import_candidate_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_mock_response_import_candidate import (
                safe_validate_provider_mock_response_import_candidate_data,
            )
            _cleaned, error = safe_validate_provider_mock_response_import_candidate_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
            # Check impossible booleans for mock response import candidate
            impossible_booleans = [
                "real_provider_response_import_candidate", "real_provider_response_imported", "real_provider_response_received",
                "provider_response_received", "provider_response_trusted", "mock_response_trusted",
                "future_response_schema_validated", "raw_response_body_stored", "raw_request_body_stored",
                "raw_prompt_body_stored", "raw_review_notes_stored", "provider_sdk_imported",
                "http_client_imported", "network_enabled", "network_call_attempted",
                "credentials_loaded", "credential_value_present", "credential_lookup_attempted",
                "env_read_attempted", "dotenv_loaded", "provider_execution_unlocked", "manual_unlock_granted",
                "provider_call_allowed", "actual_provider_call_made", "outbound_request_sent",
                "trust_upgrade_performed", "trading_signal_generated", "approval_created",
                "pending_order_created", "broker_touched",
            ]
            for b in impossible_booleans:
                if data.get(b) is True:
                    issues.append({"code": "provider_mock_response_import_candidate_impossible_boolean", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_mock_response_review_sandbox":
            for f in ("provider_mock_response_review_sandbox_id", "source_provider_mock_response_import_candidate_id", "symbol", "provider_id", "model_id", "mock_review_sandbox_status", "mock_review_sandbox_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_mock_response_review_sandbox import (
                safe_validate_provider_mock_response_review_sandbox_data,
            )
            _cleaned, error = safe_validate_provider_mock_response_review_sandbox_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
            # Check impossible booleans for mock response review sandbox
            impossible_booleans = [
                "real_provider_response_reviewed", "real_provider_response_imported", "real_provider_response_received",
                "provider_response_received", "provider_response_imported", "provider_response_reviewed",
                "provider_response_trusted", "mock_response_trusted", "review_result_present",
                "manual_review_gate_open", "manual_review_completed", "review_decision_allows_use",
                "review_decision_allows_trust_upgrade", "review_decision_allows_trading_interpretation",
                "review_decision_allows_order_creation", "review_decision_allows_order_approval",
                "review_decision_allows_broker_call", "future_response_schema_validated",
                "raw_response_body_stored", "raw_request_body_stored", "raw_prompt_body_stored",
                "raw_review_notes_stored", "provider_sdk_imported", "http_client_imported",
                "network_enabled", "network_call_attempted", "credentials_loaded",
                "credential_value_present", "credential_lookup_attempted", "env_read_attempted",
                "dotenv_loaded", "provider_execution_unlocked", "manual_unlock_granted",
                "provider_call_allowed", "actual_provider_call_made", "outbound_request_sent",
            ]
            for b in impossible_booleans:
                if data.get(b) is True:
                    issues.append({"code": "provider_mock_response_review_sandbox_impossible_boolean", "path": rel, "severity": "error"})
                    return
        elif expected_type == "provider_mock_response_trust_decision_blocker":
            for f in ("provider_mock_response_trust_decision_blocker_id", "source_provider_mock_response_review_sandbox_id", "symbol", "provider_id", "model_id", "trust_decision_blocker_status", "trust_decision_blocker_state"):
                if f not in data:
                    issues.append({"code": "missing_required_fields", "path": rel, "severity": "error"})
                    return
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
                safe_validate_provider_mock_response_trust_decision_blocker_data,
            )
            _cleaned, error = safe_validate_provider_mock_response_trust_decision_blocker_data(data, workspace_path)
            if error:
                issues.append({"code": error, "path": rel, "severity": "error"})
                return
            raw_text = path.read_text(encoding="utf-8")
            if any(frag in raw_text for frag in FORBIDDEN_FRAGMENTS):
                issues.append({"code": "forbidden_fragments", "path": rel, "severity": "error"})
                return
            # Check impossible booleans for mock response trust decision blocker
            impossible_booleans = [
                "trust_decision_present", "trust_decision_granted", "trust_decision_denied",
                "trust_upgrade_available", "trust_upgrade_performed",
                "real_provider_response_reviewed", "real_provider_response_imported", "real_provider_response_received",
                "provider_response_received", "provider_response_imported", "provider_response_reviewed",
                "provider_response_trusted", "mock_response_trusted", "review_result_present",
                "manual_review_gate_open", "manual_review_completed", "review_decision_allows_use",
                "review_decision_allows_trust_upgrade", "review_decision_allows_trading_interpretation",
                "review_decision_allows_order_creation", "review_decision_allows_order_approval",
                "review_decision_allows_broker_call", "future_response_schema_validated",
                "raw_response_body_stored", "raw_request_body_stored", "raw_prompt_body_stored",
                "raw_review_notes_stored", "provider_sdk_imported", "http_client_imported",
                "network_enabled", "network_call_attempted", "credentials_loaded",
                "credential_value_present", "credential_lookup_attempted", "env_read_attempted",
                "dotenv_loaded", "provider_execution_unlocked", "manual_unlock_granted",
                "provider_call_allowed", "actual_provider_call_made", "outbound_request_sent",
                "trading_signal_generated", "approval_created", "pending_order_created", "broker_touched",
            ]
            for b in impossible_booleans:
                if data.get(b) is True:
                    issues.append({"code": "provider_mock_response_trust_decision_blocker_impossible_boolean", "path": rel, "severity": "error"})
                    return
        # Track ID for duplicate detection
        if id_field:
            raw_id = data.get(id_field, "")
            if expected_type == "research":
                run_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "plan":
                plan_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "verification":
                verification_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "evaluation":
                evaluation_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "prompt":
                prompt_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "provider_response":
                provider_response_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "response_review":
                response_review_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "dossier":
                dossier_ids.setdefault(raw_id, []).append(rel)
            elif expected_type == "sandbox_request":
                sandbox_request_ids.setdefault(raw_id, []).append(rel)
                sandbox_request_data_by_id[raw_id] = data
            elif expected_type == "provider_call_plan":
                provider_call_plan_ids.setdefault(raw_id, []).append(rel)
                provider_call_plan_data.append(data)
            elif expected_type == "provider_execution_dry_run":
                provider_execution_dry_run_ids.setdefault(raw_id, []).append(rel)
                provider_execution_dry_run_data.append(data)
            elif expected_type == "provider_execution_state":
                provider_execution_state_ids.setdefault(raw_id, []).append(rel)
                provider_execution_state_data.append(data)
            elif expected_type == "provider_execution_audit_packet":
                provider_execution_audit_packet_ids.setdefault(raw_id, []).append(rel)
                provider_execution_audit_packet_data.append(data)
            elif expected_type == "provider_execution_readiness_report":
                provider_execution_readiness_report_ids.setdefault(raw_id, []).append(rel)
                provider_execution_readiness_report_data.append(data)
            elif expected_type == "provider_preflight_freeze":
                provider_preflight_freeze_ids.setdefault(raw_id, []).append(rel)
                provider_preflight_freeze_data.append(data)
            elif expected_type == "provider_opt_in_policy":
                provider_opt_in_policy_ids.setdefault(raw_id, []).append(rel)
                provider_opt_in_policy_data.append(data)
            elif expected_type == "provider_credential_boundary":
                provider_credential_boundary_ids.setdefault(raw_id, []).append(rel)
                provider_credential_boundary_data.append(data)
            elif expected_type == "provider_outbound_payload_preview":
                provider_outbound_payload_preview_ids.setdefault(raw_id, []).append(rel)
                provider_outbound_payload_preview_data.append(data)
            elif expected_type == "provider_response_intake_policy":
                provider_response_intake_policy_ids.setdefault(raw_id, []).append(rel)
                provider_response_intake_policy_data.append(data)
            elif expected_type == "provider_request_response_pairing":
                provider_request_response_pairing_ids.setdefault(raw_id, []).append(rel)
                provider_request_response_pairing_data.append(data)
            elif expected_type == "provider_response_schema_contract":
                provider_response_schema_contract_ids.setdefault(raw_id, []).append(rel)
                provider_response_schema_contract_data.append(data)
            elif expected_type == "provider_response_review_result":
                provider_response_review_result_ids.setdefault(raw_id, []).append(rel)
                provider_response_review_result_data.append(data)
            elif expected_type == "provider_execution_unlock_state":
                provider_execution_unlock_state_ids.setdefault(raw_id, []).append(rel)
                provider_execution_unlock_state_data.append(data)
            elif expected_type == "provider_adapter_interface_contract":
                provider_adapter_interface_contract_ids.setdefault(raw_id, []).append(rel)
                provider_adapter_interface_contract_data.append(data)
            elif expected_type == "provider_mock_response_simulation":
                provider_mock_response_simulation_ids.setdefault(raw_id, []).append(rel)
                provider_mock_response_simulation_data.append(data)
            elif expected_type == "provider_mock_response_import_candidate":
                provider_mock_response_import_candidate_ids.setdefault(raw_id, []).append(rel)
                provider_mock_response_import_candidate_data.append(data)
            elif expected_type == "provider_mock_response_review_sandbox":
                provider_mock_response_review_sandbox_ids.setdefault(raw_id, []).append(rel)
                provider_mock_response_review_sandbox_data.append(data)
            elif expected_type == "provider_mock_response_trust_decision_blocker":
                provider_mock_response_trust_decision_blocker_ids.setdefault(raw_id, []).append(rel)
                provider_mock_response_trust_decision_blocker_data.append(data)
            elif expected_type == "provider_mock_response_final_safety_seal":
                provider_mock_response_final_safety_seal_ids.setdefault(raw_id, []).append(rel)
                provider_mock_response_final_safety_seal_data.append(data)
            elif expected_type == "release_candidate_readiness_report":
                release_candidate_readiness_report_ids.setdefault(raw_id, []).append(rel)
                release_candidate_readiness_report_data.append(data)
        # Count
        if expected_type == "research":
            counts["research"] += 1
        elif expected_type == "plan":
            counts["plans"] += 1
        elif expected_type == "verification":
            counts["verifications"] += 1
        elif expected_type == "evaluation":
            counts["evaluations"] += 1
        elif expected_type == "prompt":
            counts["prompts"] += 1
        elif expected_type == "provider_response":
            counts["provider_responses"] += 1
        elif expected_type == "response_review":
            counts["response_reviews"] += 1
        elif expected_type == "dossier":
            counts["dossiers"] += 1
        elif expected_type == "sandbox_request":
            counts["sandbox_requests"] += 1
        elif expected_type == "provider_call_plan":
            counts["provider_call_plans"] += 1
        elif expected_type == "provider_execution_dry_run":
            counts["provider_execution_dry_runs"] += 1
        elif expected_type == "provider_execution_state":
            counts["provider_execution_states"] += 1
        elif expected_type == "provider_execution_audit_packet":
            counts["provider_execution_audit_packets"] += 1
        elif expected_type == "provider_execution_readiness_report":
            counts["provider_execution_readiness_reports"] += 1
        elif expected_type == "provider_preflight_freeze":
            counts["provider_preflight_freezes"] += 1
        elif expected_type == "provider_opt_in_policy":
            counts["provider_opt_in_policies"] += 1
        elif expected_type == "provider_credential_boundary":
            counts["provider_credential_boundaries"] += 1
        elif expected_type == "provider_outbound_payload_preview":
            counts["provider_outbound_payload_previews"] += 1
        elif expected_type == "provider_response_intake_policy":
            counts["provider_response_intake_policies"] += 1
        elif expected_type == "provider_request_response_pairing":
            counts["provider_request_response_pairings"] += 1
        elif expected_type == "provider_response_schema_contract":
            counts["provider_response_schema_contracts"] += 1
        elif expected_type == "provider_response_review_result":
            counts["provider_response_review_results"] += 1
        elif expected_type == "provider_execution_unlock_state":
            counts["provider_execution_unlock_states"] += 1
        elif expected_type == "provider_adapter_interface_contract":
            counts["provider_adapter_interface_contracts"] += 1
        elif expected_type == "provider_mock_response_simulation":
            counts["provider_mock_response_simulations"] += 1
        elif expected_type == "provider_mock_response_import_candidate":
            counts["provider_mock_response_import_candidates"] += 1
        elif expected_type == "provider_mock_response_review_sandbox":
            counts["provider_mock_response_review_sandboxes"] += 1
        elif expected_type == "provider_mock_response_trust_decision_blocker":
            counts["provider_mock_response_trust_decision_blockers"] += 1
        elif expected_type == "provider_mock_response_final_safety_seal":
            counts["provider_mock_response_final_safety_seals"] += 1
        elif expected_type == "release_candidate_readiness_report":
            counts["release_candidate_readiness_reports"] += 1

    for sym_dir in search_symbols:
        if not sym_dir.is_dir():
            continue
        expected_symbol = sym_dir.name
        # Research artifacts directly under symbol dir
        for path in sym_dir.glob("*.json"):
            if path.is_file():
                _inspect_file(path, "research", expected_symbol)
        # Plans
        plans_dir = sym_dir / "plans"
        if plans_dir.exists():
            for path in plans_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "plan", expected_symbol)
        # Verifications
        verifications_dir = sym_dir / "verifications"
        if verifications_dir.exists():
            for path in verifications_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "verification", expected_symbol)
        # Evaluations
        evaluations_dir = sym_dir / "evaluations"
        if evaluations_dir.exists():
            for path in evaluations_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "evaluation", expected_symbol)
        # Prompts
        prompts_dir = sym_dir / "prompts"
        if prompts_dir.exists():
            for path in prompts_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "prompt", expected_symbol)
        # Provider responses
        responses_dir = sym_dir / "provider_responses"
        if responses_dir.exists():
            for path in responses_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_response", expected_symbol)
        # Response reviews
        reviews_dir = sym_dir / "response_reviews"
        if reviews_dir.exists():
            for path in reviews_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "response_review", expected_symbol)
        # Dossiers
        dossiers_dir = sym_dir / "dossiers"
        if dossiers_dir.exists():
            for path in dossiers_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "dossier", expected_symbol)
        # Sandbox requests
        sandbox_requests_dir = sym_dir / "sandbox_requests"
        if sandbox_requests_dir.exists():
            for path in sandbox_requests_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "sandbox_request", expected_symbol)
        # Provider call plans
        provider_call_plans_dir = sym_dir / "provider_call_plans"
        if provider_call_plans_dir.exists():
            for path in provider_call_plans_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_call_plan", expected_symbol)
        # Provider execution dry-runs
        provider_execution_dry_runs_dir = sym_dir / "provider_execution_dry_runs"
        if provider_execution_dry_runs_dir.exists():
            for path in provider_execution_dry_runs_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_execution_dry_run", expected_symbol)
        # Provider execution states
        provider_execution_states_dir = sym_dir / "provider_execution_states"
        if provider_execution_states_dir.exists():
            for path in provider_execution_states_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_execution_state", expected_symbol)
        # Provider execution audit packets
        provider_execution_audit_packets_dir = sym_dir / "provider_execution_audit_packets"
        if provider_execution_audit_packets_dir.exists():
            for path in provider_execution_audit_packets_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_execution_audit_packet", expected_symbol)
        # Provider execution readiness reports
        provider_execution_readiness_reports_dir = sym_dir / "provider_execution_readiness_reports"
        if provider_execution_readiness_reports_dir.exists():
            for path in provider_execution_readiness_reports_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_execution_readiness_report", expected_symbol)
        # Provider preflight freezes
        provider_preflight_freezes_dir = sym_dir / "provider_preflight_freezes"
        if provider_preflight_freezes_dir.exists():
            for path in provider_preflight_freezes_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_preflight_freeze", expected_symbol)
        # Provider opt-in policies
        provider_opt_in_policies_dir = sym_dir / "provider_opt_in_policies"
        if provider_opt_in_policies_dir.exists():
            for path in provider_opt_in_policies_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_opt_in_policy", expected_symbol)
        # Provider credential boundaries
        provider_credential_boundaries_dir = sym_dir / "provider_credential_boundaries"
        if provider_credential_boundaries_dir.exists():
            for path in provider_credential_boundaries_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_credential_boundary", expected_symbol)
        # Provider outbound payload previews
        provider_outbound_payload_previews_dir = sym_dir / "provider_outbound_payload_previews"
        if provider_outbound_payload_previews_dir.exists():
            for path in provider_outbound_payload_previews_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_outbound_payload_preview", expected_symbol)
        # Provider response intake policies
        provider_response_intake_policies_dir = sym_dir / "provider_response_intake_policies"
        if provider_response_intake_policies_dir.exists():
            for path in provider_response_intake_policies_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_response_intake_policy", expected_symbol)
        # Provider request/response pairings
        provider_request_response_pairings_dir = sym_dir / "provider_request_response_pairings"
        if provider_request_response_pairings_dir.exists():
            for path in provider_request_response_pairings_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_request_response_pairing", expected_symbol)
        # Provider response schema contracts
        provider_response_schema_contracts_dir = sym_dir / "provider_response_schema_contracts"
        if provider_response_schema_contracts_dir.exists():
            for path in provider_response_schema_contracts_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_response_schema_contract", expected_symbol)
        # Provider response review results
        provider_response_review_results_dir = sym_dir / "provider_response_review_results"
        if provider_response_review_results_dir.exists():
            for path in provider_response_review_results_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_response_review_result", expected_symbol)
        # Provider execution unlock states
        provider_execution_unlock_states_dir = sym_dir / "provider_execution_unlock_states"
        if provider_execution_unlock_states_dir.exists():
            for path in provider_execution_unlock_states_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_execution_unlock_state", expected_symbol)
        # Provider adapter interface contracts
        provider_adapter_interface_contracts_dir = sym_dir / "provider_adapter_interface_contracts"
        if provider_adapter_interface_contracts_dir.exists():
            for path in provider_adapter_interface_contracts_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_adapter_interface_contract", expected_symbol)
        # Provider mock response simulations
        provider_mock_response_simulations_dir = sym_dir / "provider_mock_response_simulations"
        if provider_mock_response_simulations_dir.exists():
            for path in provider_mock_response_simulations_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_mock_response_simulation", expected_symbol)
        # Provider mock response import candidates
        provider_mock_response_import_candidates_dir = sym_dir / "provider_mock_response_import_candidates"
        if provider_mock_response_import_candidates_dir.exists():
            for path in provider_mock_response_import_candidates_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_mock_response_import_candidate", expected_symbol)
        # Provider mock response review sandboxes
        provider_mock_response_review_sandboxes_dir = sym_dir / "provider_mock_response_review_sandboxes"
        if provider_mock_response_review_sandboxes_dir.exists():
            for path in provider_mock_response_review_sandboxes_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_mock_response_review_sandbox", expected_symbol)
        # Provider mock response trust decision blockers
        provider_mock_response_trust_decision_blockers_dir = sym_dir / "provider_mock_response_trust_decision_blockers"
        if provider_mock_response_trust_decision_blockers_dir.exists():
            for path in provider_mock_response_trust_decision_blockers_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_mock_response_trust_decision_blocker", expected_symbol)
        # Provider mock response final safety seals
        provider_mock_response_final_safety_seals_dir = sym_dir / "provider_mock_response_final_safety_seals"
        if provider_mock_response_final_safety_seals_dir.exists():
            for path in provider_mock_response_final_safety_seals_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "provider_mock_response_final_safety_seal", expected_symbol)
        # Release candidate readiness reports
        release_candidate_readiness_reports_dir = sym_dir / "release_candidate_readiness_reports"
        if release_candidate_readiness_reports_dir.exists():
            for path in release_candidate_readiness_reports_dir.glob("*.json"):
                if path.is_file():
                    _inspect_file(path, "release_candidate_readiness_report", expected_symbol)

    # Duplicate detection
    for rid, paths in run_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pid, paths in plan_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for vid, paths in verification_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for eid, paths in evaluation_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pid, paths in prompt_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for prid, paths in provider_response_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for rrid, paths in response_review_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for did, paths in dossier_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for srid, paths in sandbox_request_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pcid, paths in provider_call_plan_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pedid, paths in provider_execution_dry_run_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pesid, paths in provider_execution_state_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for peapid, paths in provider_execution_audit_packet_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for perrid, paths in provider_execution_readiness_report_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for ppfid, paths in provider_preflight_freeze_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for popid, paths in provider_opt_in_policy_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pcbid, paths in provider_credential_boundary_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for ppid, paths in provider_outbound_payload_preview_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pipid, paths in provider_response_intake_policy_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for prpid, paths in provider_request_response_pairing_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for prscid, paths in provider_response_schema_contract_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for prrrid, paths in provider_response_review_result_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for puesid, paths in provider_execution_unlock_state_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for cid, paths in provider_adapter_interface_contract_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pmrsid, paths in provider_mock_response_simulation_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pmrcid, paths in provider_mock_response_import_candidate_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pmrsbid, paths in provider_mock_response_review_sandbox_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pmtbid, paths in provider_mock_response_trust_decision_blocker_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})
    for pmfsid, paths in provider_mock_response_final_safety_seal_ids.items():
        if len(paths) > 1:
            for p in paths:
                issues.append({"code": "duplicate_id", "path": p, "severity": "error"})

    # Provider mock response final safety seal lineage checks
    provider_mock_response_trust_decision_blocker_data_by_id: dict[str, dict[str, Any]] = {}
    for pmtb in provider_mock_response_trust_decision_blocker_data:
        pmtb_id = pmtb.get("provider_mock_response_trust_decision_blocker_id", "")
        if pmtb_id:
            provider_mock_response_trust_decision_blocker_data_by_id[pmtb_id] = pmtb

    for seal in provider_mock_response_final_safety_seal_data:
        rel = seal.get("artifact_path", "")
        src_blocker_id = seal.get("source_trust_decision_blocker_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_blocker_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source trust decision blocker
        if src_blocker_id not in provider_mock_response_trust_decision_blocker_data_by_id:
            issues.append({"code": "missing_source_trust_decision_blocker", "path": rel, "severity": "error"})
            continue
        # Source trust decision blocker hash mismatch
        stored_src_hash = seal.get("source_trust_decision_blocker_hash", "")
        if stored_src_hash:
            src_blocker = provider_mock_response_trust_decision_blocker_data_by_id[src_blocker_id]
            actual_blocker_hash = src_blocker.get("artifact_hash", "")
            if actual_blocker_hash != stored_src_hash:
                issues.append({"code": "source_trust_decision_blocker_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Source provider_id must be mock
        if src_blocker_id in provider_mock_response_trust_decision_blocker_data_by_id:
            src_tb = provider_mock_response_trust_decision_blocker_data_by_id[src_blocker_id]
            if src_tb.get("provider_id") != "mock":
                issues.append({"code": "provider_mock_response_final_safety_seal_source_trust_decision_blocker_provider_not_mock", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in final safety seal
        impossible_booleans = [
            "real_provider_response_imported", "real_provider_response_received",
            "provider_response_received", "provider_response_trusted", "mock_response_trusted",
            "network_enabled", "network_call_attempted", "credentials_loaded",
            "provider_call_allowed", "actual_provider_call_made",
            "trading_signal_generated", "approval_created", "pending_order_created", "broker_touched",
            "seal_authorizing", "seal_allows_execution", "seal_allows_trading",
        ]
        for b in impossible_booleans:
            if seal.get(b) is not False:
                issues.append({"code": "provider_mock_response_final_safety_seal_impossible_boolean", "path": rel, "severity": "error"})
                break

    # Provider mock response import candidate lineage checks
    provider_mock_response_simulation_data_by_id: dict[str, dict[str, Any]] = {}
    for pmrs in provider_mock_response_simulation_data:
        pmrs_id = pmrs.get("provider_mock_response_simulation_id", "")
        if pmrs_id:
            provider_mock_response_simulation_data_by_id[pmrs_id] = pmrs

    for candidate in provider_mock_response_import_candidate_data:
        rel = candidate.get("artifact_path", "")
        src_mock_simulation_id = candidate.get("source_provider_mock_response_simulation_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_mock_simulation_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source mock response simulation
        if src_mock_simulation_id not in provider_mock_response_simulation_data_by_id:
            issues.append({"code": "missing_source_mock_response_simulation", "path": rel, "severity": "error"})
            continue
        # Source mock response simulation hash mismatch
        stored_src_hash = candidate.get("source_mock_response_simulation_hash", "")
        if stored_src_hash:
            src_mock_simulation = provider_mock_response_simulation_data_by_id[src_mock_simulation_id]
            actual_mock_simulation_hash = src_mock_simulation.get("artifact_hash", "")
            if actual_mock_simulation_hash != stored_src_hash:
                issues.append({"code": "source_mock_response_simulation_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Source provider_id must be mock
        if src_mock_simulation_id in provider_mock_response_simulation_data_by_id:
            src_ms = provider_mock_response_simulation_data_by_id[src_mock_simulation_id]
            if src_ms.get("provider_id") != "mock":
                issues.append({"code": "provider_mock_response_import_candidate_source_mock_response_provider_not_mock", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in import candidate
        impossible_booleans = [
            "real_provider_response_import_candidate", "real_provider_response_imported", "real_provider_response_received",
            "provider_response_received", "provider_response_trusted", "mock_response_trusted",
            "future_response_schema_validated", "raw_response_body_stored", "provider_sdk_imported",
            "http_client_imported", "network_enabled", "network_call_attempted",
            "credentials_loaded", "provider_call_allowed", "actual_provider_call_made",
            "trading_signal_generated", "approval_created", "pending_order_created", "broker_touched",
        ]
        for b in impossible_booleans:
            if candidate.get(b) is not False:
                issues.append({"code": "provider_mock_response_import_candidate_impossible_boolean", "path": rel, "severity": "error"})
                break

    # Provider mock response review sandbox lineage checks
    provider_mock_response_import_candidate_data_by_id: dict[str, dict[str, Any]] = {}
    for pmrc in provider_mock_response_import_candidate_data:
        pmrc_id = pmrc.get("provider_mock_response_import_candidate_id", "")
        if pmrc_id:
            provider_mock_response_import_candidate_data_by_id[pmrc_id] = pmrc

    for sandbox in provider_mock_response_review_sandbox_data:
        rel = sandbox.get("artifact_path", "")
        src_import_candidate_id = sandbox.get("source_provider_mock_response_import_candidate_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_import_candidate_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source mock import candidate
        if src_import_candidate_id not in provider_mock_response_import_candidate_data_by_id:
            issues.append({"code": "missing_source_mock_import_candidate", "path": rel, "severity": "error"})
            continue
        # Source mock import candidate hash mismatch
        stored_src_hash = sandbox.get("source_mock_import_candidate_hash", "")
        if stored_src_hash:
            src_import_candidate = provider_mock_response_import_candidate_data_by_id[src_import_candidate_id]
            actual_import_candidate_hash = src_import_candidate.get("artifact_hash", "")
            if actual_import_candidate_hash != stored_src_hash:
                issues.append({"code": "source_mock_import_candidate_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Source provider_id must be mock
        if src_import_candidate_id in provider_mock_response_import_candidate_data_by_id:
            src_ic = provider_mock_response_import_candidate_data_by_id[src_import_candidate_id]
            if src_ic.get("provider_id") != "mock":
                issues.append({"code": "provider_mock_response_review_sandbox_source_import_candidate_provider_not_mock", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in review sandbox
        impossible_booleans = [
            "real_provider_response_reviewed", "real_provider_response_imported", "real_provider_response_received",
            "provider_response_received", "provider_response_imported", "provider_response_reviewed",
            "provider_response_trusted", "mock_response_trusted", "review_result_present",
            "manual_review_gate_open", "manual_review_completed", "review_decision_allows_use",
            "review_decision_allows_trust_upgrade", "review_decision_allows_trading_interpretation",
            "review_decision_allows_order_creation", "review_decision_allows_order_approval",
            "review_decision_allows_broker_call", "future_response_schema_validated",
            "raw_response_body_stored", "raw_request_body_stored", "raw_prompt_body_stored",
            "raw_review_notes_stored", "provider_sdk_imported", "http_client_imported",
            "network_enabled", "network_call_attempted", "credentials_loaded",
            "credential_value_present", "credential_lookup_attempted", "env_read_attempted",
            "dotenv_loaded", "provider_execution_unlocked", "manual_unlock_granted",
            "provider_call_allowed", "actual_provider_call_made", "outbound_request_sent",
            "trust_upgrade_performed", "trading_signal_generated", "approval_created",
            "pending_order_created", "broker_touched",
        ]
        for b in impossible_booleans:
            if sandbox.get(b) is not False:
                issues.append({"code": "provider_mock_response_review_sandbox_impossible_boolean", "path": rel, "severity": "error"})
                break

    # Provider call plan lineage checks
    for plan in provider_call_plan_data:
        rel = plan.get("artifact_path", "")
        src_sandbox_id = plan.get("source_sandbox_request_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_sandbox_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source sandbox
        if src_sandbox_id not in sandbox_request_data_by_id:
            issues.append({"code": "missing_source_sandbox", "path": rel, "severity": "error"})
            continue
        # Source sandbox hash mismatch
        stored_src_hash = plan.get("source_sandbox_hash", "")
        if stored_src_hash:
            src_sandbox = sandbox_request_data_by_id[src_sandbox_id]
            computed_src_hash = artifact_sha256(src_sandbox)
            if computed_src_hash != stored_src_hash:
                issues.append({"code": "source_sandbox_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Unknown provider target
        provider_id = plan.get("provider_id", "")
        if provider_id:
            from atlas_agent.research.provider_call_plan import _get_disabled_provider_ids
            if provider_id not in _get_disabled_provider_ids():
                issues.append({"code": "unknown_provider_target", "path": rel, "severity": "error"})

    # Provider execution dry-run lineage checks
    provider_execution_dry_run_data_by_id: dict[str, dict[str, Any]] = {}
    for ped in provider_execution_dry_run_data:
        ped_id = ped.get("provider_execution_dry_run_id", "")
        if ped_id:
            provider_execution_dry_run_data_by_id[ped_id] = ped

    # Provider execution state lineage checks
    for state in provider_execution_state_data:
        rel = state.get("artifact_path", "")
        src_dry_run_id = state.get("source_provider_execution_dry_run_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_dry_run_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source dry-run
        if src_dry_run_id not in provider_execution_dry_run_data_by_id:
            issues.append({"code": "missing_source_dry_run", "path": rel, "severity": "error"})
            continue
        # Source dry-run hash mismatch
        stored_src_hash = state.get("source_dry_run_hash", "")
        if stored_src_hash:
            src_dry_run = provider_execution_dry_run_data_by_id[src_dry_run_id]
            actual_dry_run_hash = src_dry_run.get("artifact_hash", "")
            if actual_dry_run_hash != stored_src_hash:
                issues.append({"code": "source_dry_run_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in state
        for flag in ("provider_enabled", "network_enabled", "credentials_loaded", "provider_call_allowed", "actual_provider_call_made", "future_provider_execution_possible"):
            if state.get(flag) is not False:
                issues.append({"code": "provider_execution_state_impossible_boolean", "path": rel, "severity": "error"})
                break

    # Provider execution audit packet lineage checks
    provider_execution_state_data_by_id: dict[str, dict[str, Any]] = {}
    for state in provider_execution_state_data:
        state_id = state.get("provider_execution_state_id", "")
        if state_id:
            provider_execution_state_data_by_id[state_id] = state

    for packet in provider_execution_audit_packet_data:
        rel = packet.get("artifact_path", "")
        src_state_id = packet.get("source_provider_execution_state_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_state_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source state
        if src_state_id not in provider_execution_state_data_by_id:
            issues.append({"code": "missing_source_state", "path": rel, "severity": "error"})
            continue
        # Source state hash mismatch
        stored_src_hash = packet.get("source_state_hash", "")
        if stored_src_hash:
            src_state = provider_execution_state_data_by_id[src_state_id]
            actual_state_hash = src_state.get("artifact_hash", "")
            if actual_state_hash != stored_src_hash:
                issues.append({"code": "source_state_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in audit packet
        from atlas_agent.research.provider_execution_audit_packet import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(packet)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})

    # Provider execution readiness report lineage checks
    provider_execution_audit_packet_data_by_id: dict[str, dict[str, Any]] = {}
    for packet in provider_execution_audit_packet_data:
        pkt_id = packet.get("provider_execution_audit_packet_id", "")
        if pkt_id:
            provider_execution_audit_packet_data_by_id[pkt_id] = packet

    for report in provider_execution_readiness_report_data:
        rel = report.get("artifact_path", "")
        src_audit_id = report.get("source_provider_execution_audit_packet_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_audit_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source audit packet
        if src_audit_id not in provider_execution_audit_packet_data_by_id:
            issues.append({"code": "missing_source_audit_packet", "path": rel, "severity": "error"})
            continue
        # Source audit packet hash mismatch
        stored_src_hash = report.get("source_audit_packet_hash", "")
        if stored_src_hash:
            src_audit = provider_execution_audit_packet_data_by_id[src_audit_id]
            actual_audit_hash = src_audit.get("artifact_hash", "")
            if actual_audit_hash != stored_src_hash:
                issues.append({"code": "source_audit_packet_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in readiness report
        from atlas_agent.research.provider_execution_readiness_report import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(report)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})
        # readiness_score validation
        score = report.get("readiness_score")
        if not isinstance(score, int) or score < 0 or score > 100:
            issues.append({"code": "invalid_readiness_score", "path": rel, "severity": "error"})

    # Provider preflight freeze lineage checks
    provider_execution_readiness_report_data_by_id: dict[str, dict[str, Any]] = {}
    for report in provider_execution_readiness_report_data:
        pkt_id = report.get("provider_execution_readiness_report_id", "")
        if pkt_id:
            provider_execution_readiness_report_data_by_id[pkt_id] = report

    for freeze in provider_preflight_freeze_data:
        rel = freeze.get("artifact_path", "")
        src_readiness_id = freeze.get("source_provider_execution_readiness_report_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_readiness_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source readiness report
        if src_readiness_id not in provider_execution_readiness_report_data_by_id:
            issues.append({"code": "missing_source_readiness_report", "path": rel, "severity": "error"})
            continue
        # Source readiness report hash mismatch
        stored_src_hash = freeze.get("source_readiness_report_hash", "")
        if stored_src_hash:
            src_readiness = provider_execution_readiness_report_data_by_id[src_readiness_id]
            actual_readiness_hash = src_readiness.get("artifact_hash", "")
            if actual_readiness_hash != stored_src_hash:
                issues.append({"code": "source_readiness_report_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in freeze
        from atlas_agent.research.provider_preflight_freeze import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(freeze)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})
        # readiness_score validation
        score = freeze.get("readiness_score")
        if not isinstance(score, int) or score < 0 or score > 100:
            issues.append({"code": "invalid_readiness_score", "path": rel, "severity": "error"})

    # Provider opt-in policy lineage checks
    provider_preflight_freeze_data_by_id: dict[str, dict[str, Any]] = {}
    for freeze in provider_preflight_freeze_data:
        fid = freeze.get("provider_preflight_freeze_id", "")
        if fid:
            provider_preflight_freeze_data_by_id[fid] = freeze

    for policy in provider_opt_in_policy_data:
        rel = policy.get("artifact_path", "")
        src_freeze_id = policy.get("source_provider_preflight_freeze_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_freeze_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source freeze
        if src_freeze_id not in provider_preflight_freeze_data_by_id:
            issues.append({"code": "missing_source_freeze", "path": rel, "severity": "error"})
            continue
        # Source freeze hash mismatch
        stored_freeze_hash = policy.get("source_freeze_hash", "")
        if stored_freeze_hash:
            src_freeze = provider_preflight_freeze_data_by_id[src_freeze_id]
            actual_freeze_hash = src_freeze.get("artifact_hash", "")
            if actual_freeze_hash != stored_freeze_hash:
                issues.append({"code": "source_freeze_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in policy
        from atlas_agent.research.provider_opt_in_policy import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(policy)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})

    # Provider credential boundary lineage checks
    provider_opt_in_policy_data_by_id: dict[str, dict[str, Any]] = {}
    for policy in provider_opt_in_policy_data:
        pid = policy.get("provider_opt_in_policy_id", "")
        if pid:
            provider_opt_in_policy_data_by_id[pid] = policy

    for boundary in provider_credential_boundary_data:
        rel = boundary.get("artifact_path", "")
        src_policy_id = boundary.get("source_provider_opt_in_policy_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_policy_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source policy
        if src_policy_id not in provider_opt_in_policy_data_by_id:
            issues.append({"code": "missing_source_policy", "path": rel, "severity": "error"})
            continue
        # Source policy hash mismatch
        stored_policy_hash = boundary.get("source_opt_in_policy_hash", "")
        if stored_policy_hash:
            src_policy = provider_opt_in_policy_data_by_id[src_policy_id]
            actual_policy_hash = src_policy.get("artifact_hash", "")
            if actual_policy_hash != stored_policy_hash:
                issues.append({"code": "source_policy_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in boundary
        from atlas_agent.research.provider_credential_boundary import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(boundary)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})

    # Provider outbound payload preview lineage checks
    provider_credential_boundary_data_by_id: dict[str, dict[str, Any]] = {}
    for boundary in provider_credential_boundary_data:
        bid = boundary.get("provider_credential_boundary_id", "")
        if bid:
            provider_credential_boundary_data_by_id[bid] = boundary

    for preview in provider_outbound_payload_preview_data:
        rel = preview.get("artifact_path", "")
        src_boundary_id = preview.get("source_provider_credential_boundary_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_boundary_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source credential boundary
        if src_boundary_id not in provider_credential_boundary_data_by_id:
            issues.append({"code": "missing_source_credential_boundary", "path": rel, "severity": "error"})
            continue
        # Source credential boundary hash mismatch
        stored_boundary_hash = preview.get("source_credential_boundary_hash", "")
        if stored_boundary_hash:
            src_boundary = provider_credential_boundary_data_by_id[src_boundary_id]
            actual_boundary_hash = src_boundary.get("artifact_hash", "")
            if actual_boundary_hash != stored_boundary_hash:
                issues.append({"code": "source_credential_boundary_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in payload preview
        from atlas_agent.research.provider_outbound_payload_preview import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(preview)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})

    # Provider response intake policy lineage checks
    provider_outbound_payload_preview_data_by_id: dict[str, dict[str, Any]] = {}
    for preview in provider_outbound_payload_preview_data:
        pid = preview.get("provider_outbound_payload_preview_id", "")
        if pid:
            provider_outbound_payload_preview_data_by_id[pid] = preview

    for policy in provider_response_intake_policy_data:
        rel = policy.get("artifact_path", "")
        src_preview_id = policy.get("source_provider_outbound_payload_preview_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_preview_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source payload preview
        if src_preview_id not in provider_outbound_payload_preview_data_by_id:
            issues.append({"code": "missing_source_payload_preview", "path": rel, "severity": "error"})
            continue
        # Source payload preview hash mismatch
        stored_preview_hash = policy.get("source_payload_preview_hash", "")
        if stored_preview_hash:
            src_preview = provider_outbound_payload_preview_data_by_id[src_preview_id]
            actual_preview_hash = src_preview.get("artifact_hash", "")
            if actual_preview_hash != stored_preview_hash:
                issues.append({"code": "source_payload_preview_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in intake policy
        from atlas_agent.research.provider_response_intake_policy import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(policy)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})

    # Provider request response pairing lineage checks
    provider_response_intake_policy_data_by_id: dict[str, dict[str, Any]] = {}
    for policy in provider_response_intake_policy_data:
        pid = policy.get("provider_response_intake_policy_id", "")
        if pid:
            provider_response_intake_policy_data_by_id[pid] = policy

    for pairing in provider_request_response_pairing_data:
        rel = pairing.get("artifact_path", "")
        src_intake_id = pairing.get("source_provider_response_intake_policy_id", "")
        # Invalid lineage
        try:
            validate_run_id(src_intake_id)
        except ResearchSessionError:
            issues.append({"code": "invalid_lineage", "path": rel, "severity": "error"})
            continue
        # Missing source response intake policy
        if src_intake_id not in provider_response_intake_policy_data_by_id:
            issues.append({"code": "missing_source_response_intake_policy", "path": rel, "severity": "error"})
            continue
        # Source response intake policy hash mismatch
        stored_intake_hash = pairing.get("source_response_intake_policy_hash", "")
        if stored_intake_hash:
            src_intake = provider_response_intake_policy_data_by_id[src_intake_id]
            actual_intake_hash = src_intake.get("artifact_hash", "")
            if actual_intake_hash != stored_intake_hash:
                issues.append({"code": "source_response_intake_policy_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Missing source payload preview
        src_preview_id = pairing.get("source_provider_outbound_payload_preview_id", "")
        if src_preview_id not in provider_outbound_payload_preview_data_by_id:
            issues.append({"code": "missing_source_payload_preview", "path": rel, "severity": "error"})
            continue
        # Source payload preview hash mismatch
        stored_preview_hash = pairing.get("source_payload_preview_hash", "")
        if stored_preview_hash:
            src_preview = provider_outbound_payload_preview_data_by_id[src_preview_id]
            actual_preview_hash = src_preview.get("artifact_hash", "")
            if actual_preview_hash != stored_preview_hash:
                issues.append({"code": "source_payload_preview_hash_mismatch", "path": rel, "severity": "error"})
                continue
        # Impossible booleans in pairing
        from atlas_agent.research.provider_request_response_pairing import _check_boolean_safety_flags
        error = _check_boolean_safety_flags(pairing)
        if error:
            issues.append({"code": error, "path": rel, "severity": "error"})

    return {
        "ok": True,
        "status": "research_artifacts_checked",
        "counts": counts,
        "issues": issues,
        "warnings": warnings,
    }


def _iter_verification_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return verification artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "verifications")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                v_dir = sym_dir / "verifications"
                if v_dir.exists():
                    search_dirs.append(v_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "verification_id": data.get("verification_id", path.stem),
                    "source_plan_id": data.get("source_plan_id", ""),
                    "recommendation": data.get("recommendation", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items


def _iter_evaluation_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return evaluation artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "evaluations")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                e_dir = sym_dir / "evaluations"
                if e_dir.exists():
                    search_dirs.append(e_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "evaluation_id": data.get("evaluation_id", path.stem),
                    "source_plan_id": data.get("source_plan_id", ""),
                    "recommendation": data.get("recommendation", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items


def _iter_prompt_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return prompt packet artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "prompts")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                p_dir = sym_dir / "prompts"
                if p_dir.exists():
                    search_dirs.append(p_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "prompt_packet_id": data.get("prompt_packet_id", path.stem),
                    "source_run_id": data.get("source_run_id", ""),
                    "symbol": data.get("symbol", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items


def _iter_sandbox_request_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return sandbox request artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "sandbox_requests")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                s_dir = sym_dir / "sandbox_requests"
                if s_dir.exists():
                    search_dirs.append(s_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "sandbox_request_id": data.get("sandbox_request_id", path.stem),
                    "prompt_packet_id": data.get("prompt_packet_id", ""),
                    "source_run_id": data.get("source_run_id", ""),
                    "symbol": data.get("symbol", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items


def find_sandbox_request_by_id(workspace_path: Path, sandbox_request_id: str) -> Path | None:
    """Find exactly one sandbox request artifact by sandbox_request_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_id = validate_run_id(sandbox_request_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        sandbox_dir = sym_dir / "sandbox_requests"
        if not sandbox_dir.exists():
            continue
        candidate = sandbox_dir / f"{safe_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_sandbox_request_id")
    return matches[0]


def load_sandbox_request(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a sandbox request JSON safely."""
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("sandbox_request_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("sandbox_request_malformed")
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_sandbox_schema")
    return data


def _iter_provider_response_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return provider response artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "provider_responses")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                r_dir = sym_dir / "provider_responses"
                if r_dir.exists():
                    search_dirs.append(r_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "provider_response_id": data.get("provider_response_id", path.stem),
                    "source_prompt_packet_id": data.get("source_prompt_packet_id", ""),
                    "source_run_id": data.get("source_run_id", ""),
                    "provider": data.get("provider", "unknown"),
                    "recommendation": data.get("recommendation", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items


def _iter_response_review_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return response review artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "response_reviews")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                r_dir = sym_dir / "response_reviews"
                if r_dir.exists():
                    search_dirs.append(r_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "response_review_id": data.get("response_review_id", path.stem),
                    "source_provider_response_id": data.get("source_provider_response_id", ""),
                    "source_prompt_packet_id": data.get("source_prompt_packet_id", ""),
                    "source_run_id": data.get("source_run_id", ""),
                    "provider": data.get("provider", "unknown"),
                    "recommendation": data.get("recommendation", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items


def build_research_timeline(
    workspace_path: Path,
    *,
    symbol_filter: str | None = None,
    run_id_filter: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Build a read-only lineage timeline of research artifacts and their descendants.

    Links research -> plans -> verifications and evaluations.
    Never modifies artifacts.
    """
    if limit < 1:
        raise ResearchSessionError("limit_must_be_positive")
    if limit > 100:
        limit = 100

    warnings: list[dict[str, str]] = []

    # Load all artifact types
    research_items = iter_research_artifacts(workspace_path, symbol=symbol_filter)
    plan_items = iter_plan_artifacts(workspace_path, symbol=symbol_filter)
    verification_items = _iter_verification_artifacts(workspace_path, symbol=symbol_filter)
    evaluation_items = _iter_evaluation_artifacts(workspace_path, symbol=symbol_filter)
    prompt_items = _iter_prompt_artifacts(workspace_path, symbol=symbol_filter)
    provider_response_items = _iter_provider_response_artifacts(workspace_path, symbol=symbol_filter)
    response_review_items = _iter_response_review_artifacts(workspace_path, symbol=symbol_filter)
    dossier_items = _iter_dossier_artifacts(workspace_path, symbol=symbol_filter)
    sandbox_request_items = _iter_sandbox_request_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_call_plan import iter_provider_call_plan_artifacts
    provider_call_plan_items = iter_provider_call_plan_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_execution_dry_run import iter_provider_execution_dry_run_artifacts
    provider_execution_dry_run_items = iter_provider_execution_dry_run_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_execution_state import iter_provider_execution_state_artifacts
    provider_execution_state_items = iter_provider_execution_state_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_execution_audit_packet import iter_provider_execution_audit_packet_artifacts
    provider_execution_audit_packet_items = iter_provider_execution_audit_packet_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_execution_readiness_report import iter_provider_execution_readiness_report_artifacts
    provider_execution_readiness_report_items = iter_provider_execution_readiness_report_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_preflight_freeze import iter_provider_preflight_freeze_artifacts
    provider_preflight_freeze_items = iter_provider_preflight_freeze_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_opt_in_policy import iter_provider_opt_in_policy_artifacts
    provider_opt_in_policy_items = iter_provider_opt_in_policy_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_credential_boundary import iter_provider_credential_boundary_artifacts
    provider_credential_boundary_items = iter_provider_credential_boundary_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_outbound_payload_preview import iter_provider_outbound_payload_preview_artifacts
    provider_outbound_payload_preview_items = iter_provider_outbound_payload_preview_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_response_intake_policy import iter_provider_response_intake_policy_artifacts
    provider_response_intake_policy_items = iter_provider_response_intake_policy_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_request_response_pairing import iter_provider_request_response_pairing_artifacts
    provider_request_response_pairing_items = iter_provider_request_response_pairing_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_response_schema_contract import iter_provider_response_schema_contract_artifacts
    provider_response_schema_contract_items = iter_provider_response_schema_contract_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_response_review_result import iter_provider_response_review_result_artifacts
    provider_response_review_result_items = iter_provider_response_review_result_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_execution_unlock_state import iter_provider_execution_unlock_state_artifacts
    provider_execution_unlock_state_items = iter_provider_execution_unlock_state_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_adapter_interface_contract import iter_provider_adapter_interface_contract_artifacts
    provider_adapter_interface_contract_items = iter_provider_adapter_interface_contract_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_mock_response_simulation import iter_provider_mock_response_simulation_artifacts
    provider_mock_response_simulation_items = iter_provider_mock_response_simulation_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.provider_mock_response_import_candidate import iter_provider_mock_response_import_candidate_artifacts
    provider_mock_response_import_candidate_items = iter_provider_mock_response_import_candidate_artifacts(workspace_path, symbol=symbol_filter)
    from atlas_agent.research.release_candidate_readiness import iter_release_candidate_readiness_artifacts
    release_candidate_readiness_items = iter_release_candidate_readiness_artifacts(workspace_path, symbol=symbol_filter)

    # Index plans by source_run_id
    plans_by_run_id: dict[str, list[dict[str, Any]]] = {}
    for plan in plan_items:
        if plan.get("_malformed"):
            continue
        src = plan.get("source_run_id", "")
        if src:
            plans_by_run_id.setdefault(src, []).append(plan)
        else:
            warnings.append({"code": "orphan_plan", "path": plan.get("artifact_path", ""), "severity": "warning"})

    # Index verifications by source_plan_id
    verifications_by_plan_id: dict[str, list[dict[str, Any]]] = {}
    for v in verification_items:
        src = v.get("source_plan_id", "")
        if src:
            verifications_by_plan_id.setdefault(src, []).append(v)
        else:
            warnings.append({"code": "orphan_verification", "path": v.get("artifact_path", ""), "severity": "warning"})

    # Index evaluations by source_plan_id
    evaluations_by_plan_id: dict[str, list[dict[str, Any]]] = {}
    for e in evaluation_items:
        src = e.get("source_plan_id", "")
        if src:
            evaluations_by_plan_id.setdefault(src, []).append(e)
        else:
            warnings.append({"code": "orphan_evaluation", "path": e.get("artifact_path", ""), "severity": "warning"})

    # Index prompts by source_run_id
    prompts_by_run_id: dict[str, list[dict[str, Any]]] = {}
    for p in prompt_items:
        src = p.get("source_run_id", "")
        if src:
            prompts_by_run_id.setdefault(src, []).append(p)
        else:
            warnings.append({"code": "orphan_prompt", "path": p.get("artifact_path", ""), "severity": "warning"})

    # Index provider responses by source_prompt_packet_id
    provider_responses_by_prompt_id: dict[str, list[dict[str, Any]]] = {}
    for pr in provider_response_items:
        src = pr.get("source_prompt_packet_id", "")
        if src:
            provider_responses_by_prompt_id.setdefault(src, []).append(pr)
        else:
            warnings.append({"code": "orphan_provider_response", "path": pr.get("artifact_path", ""), "severity": "warning"})

    # Index response reviews by source_provider_response_id
    response_reviews_by_provider_id: dict[str, list[dict[str, Any]]] = {}
    for rr in response_review_items:
        src = rr.get("source_provider_response_id", "")
        if src:
            response_reviews_by_provider_id.setdefault(src, []).append(rr)
        else:
            warnings.append({"code": "orphan_response_review", "path": rr.get("artifact_path", ""), "severity": "warning"})

    # Index sandbox requests by prompt_packet_id
    sandbox_requests_by_prompt_id: dict[str, list[dict[str, Any]]] = {}
    for sr in sandbox_request_items:
        src = sr.get("prompt_packet_id", "")
        if src:
            sandbox_requests_by_prompt_id.setdefault(src, []).append(sr)
        else:
            warnings.append({"code": "orphan_sandbox_request", "path": sr.get("artifact_path", ""), "severity": "warning"})

    # Index provider call plans by source_sandbox_request_id
    provider_call_plans_by_sandbox_id: dict[str, list[dict[str, Any]]] = {}
    for pcp in provider_call_plan_items:
        src = pcp.get("source_sandbox_request_id", "")
        if src:
            provider_call_plans_by_sandbox_id.setdefault(src, []).append(pcp)
        else:
            warnings.append({"code": "orphan_provider_call_plan", "path": pcp.get("artifact_path", ""), "severity": "warning"})

    # Index provider execution dry-runs by source_provider_call_plan_id
    provider_execution_dry_runs_by_plan_id: dict[str, list[dict[str, Any]]] = {}
    for ped in provider_execution_dry_run_items:
        src = ped.get("source_provider_call_plan_id", "")
        if src:
            provider_execution_dry_runs_by_plan_id.setdefault(src, []).append(ped)
        else:
            warnings.append({"code": "orphan_provider_execution_dry_run", "path": ped.get("artifact_path", ""), "severity": "warning"})

    # Index provider execution states by source_provider_execution_dry_run_id
    provider_execution_states_by_dry_run_id: dict[str, list[dict[str, Any]]] = {}
    for pes in provider_execution_state_items:
        src = pes.get("source_provider_execution_dry_run_id", "")
        if src:
            provider_execution_states_by_dry_run_id.setdefault(src, []).append(pes)
        else:
            warnings.append({"code": "orphan_provider_execution_state", "path": pes.get("artifact_path", ""), "severity": "warning"})

    # Index provider execution audit packets by source_provider_execution_state_id
    provider_execution_audit_packets_by_state_id: dict[str, list[dict[str, Any]]] = {}
    for peap in provider_execution_audit_packet_items:
        if peap.get("_invalid"):
            # Skip invalid audit packets from timeline; they are represented by safe warning codes only
            warnings.append({"code": "invalid_provider_execution_audit_packet_skipped", "path": peap.get("artifact_path", ""), "severity": "warning"})
            continue
        src = peap.get("source_provider_execution_state_id", "")
        if src:
            provider_execution_audit_packets_by_state_id.setdefault(src, []).append(peap)
        else:
            warnings.append({"code": "orphan_provider_execution_audit_packet", "path": peap.get("artifact_path", ""), "severity": "warning"})

    # Index provider execution readiness reports by source_provider_execution_audit_packet_id
    provider_execution_readiness_reports_by_audit_id: dict[str, list[dict[str, Any]]] = {}
    for perr in provider_execution_readiness_report_items:
        if perr.get("_invalid"):
            warnings.append({"code": "invalid_provider_execution_readiness_report_skipped", "path": perr.get("artifact_path", ""), "severity": "warning"})
            continue
        src = perr.get("source_provider_execution_audit_packet_id", "")
        if src:
            provider_execution_readiness_reports_by_audit_id.setdefault(src, []).append(perr)
        else:
            warnings.append({"code": "orphan_provider_execution_readiness_report", "path": perr.get("artifact_path", ""), "severity": "warning"})

    # Index provider preflight freezes by source_provider_execution_readiness_report_id
    provider_preflight_freezes_by_readiness_id: dict[str, list[dict[str, Any]]] = {}
    for ppf in provider_preflight_freeze_items:
        if ppf.get("_invalid"):
            warnings.append({"code": "invalid_provider_preflight_freeze_skipped", "path": ppf.get("artifact_path", ""), "severity": "warning"})
            continue
        src = ppf.get("source_provider_execution_readiness_report_id", "")
        if src:
            provider_preflight_freezes_by_readiness_id.setdefault(src, []).append(ppf)
        else:
            warnings.append({"code": "orphan_provider_preflight_freeze", "path": ppf.get("artifact_path", ""), "severity": "warning"})

    provider_opt_in_policies_by_freeze_id: dict[str, list[dict[str, Any]]] = {}
    for pop in provider_opt_in_policy_items:
        if pop.get("_invalid"):
            warnings.append({"code": "invalid_provider_opt_in_policy_skipped", "path": pop.get("artifact_path", ""), "severity": "warning"})
            continue
        src = pop.get("source_provider_preflight_freeze_id", "")
        if src:
            provider_opt_in_policies_by_freeze_id.setdefault(src, []).append(pop)
        else:
            warnings.append({"code": "orphan_provider_opt_in_policy", "path": pop.get("artifact_path", ""), "severity": "warning"})

    provider_credential_boundaries_by_policy_id: dict[str, list[dict[str, Any]]] = {}
    for pcb in provider_credential_boundary_items:
        if pcb.get("_invalid"):
            warnings.append({"code": "invalid_provider_credential_boundary_skipped", "path": pcb.get("artifact_path", ""), "severity": "warning"})
            continue
        src = pcb.get("source_provider_opt_in_policy_id", "")
        if src:
            provider_credential_boundaries_by_policy_id.setdefault(src, []).append(pcb)
        else:
            warnings.append({"code": "orphan_provider_credential_boundary", "path": pcb.get("artifact_path", ""), "severity": "warning"})

    provider_outbound_payload_previews_by_boundary_id: dict[str, list[dict[str, Any]]] = {}
    for pp in provider_outbound_payload_preview_items:
        if pp.get("_invalid"):
            warnings.append({"code": "invalid_provider_outbound_payload_preview_skipped", "path": pp.get("artifact_path", ""), "severity": "warning"})
            continue
        src = pp.get("source_provider_credential_boundary_id", "")
        if src:
            provider_outbound_payload_previews_by_boundary_id.setdefault(src, []).append(pp)
        else:
            warnings.append({"code": "orphan_provider_outbound_payload_preview", "path": pp.get("artifact_path", ""), "severity": "warning"})

    provider_response_intake_policies_by_preview_id: dict[str, list[dict[str, Any]]] = {}
    for pip in provider_response_intake_policy_items:
        if pip.get("_invalid"):
            warnings.append({"code": "invalid_provider_response_intake_policy_skipped", "path": pip.get("artifact_path", ""), "severity": "warning"})
            continue
        src = pip.get("source_provider_outbound_payload_preview_id", "")
        if src:
            provider_response_intake_policies_by_preview_id.setdefault(src, []).append(pip)
        else:
            warnings.append({"code": "orphan_provider_response_intake_policy", "path": pip.get("artifact_path", ""), "severity": "warning"})

    provider_request_response_pairings_by_intake_policy_id: dict[str, list[dict[str, Any]]] = {}
    for prrp in provider_request_response_pairing_items:
        if prrp.get("_invalid"):
            warnings.append({"code": "invalid_provider_request_response_pairing_skipped", "path": prrp.get("artifact_path", ""), "severity": "warning"})
            continue
        src = prrp.get("source_provider_response_intake_policy_id", "")
        if src:
            provider_request_response_pairings_by_intake_policy_id.setdefault(src, []).append(prrp)
        else:
            warnings.append({"code": "orphan_provider_request_response_pairing", "path": prrp.get("artifact_path", ""), "severity": "warning"})

    provider_response_schema_contracts_by_pairing_id: dict[str, list[dict[str, Any]]] = {}
    for prsc in provider_response_schema_contract_items:
        if prsc.get("_invalid"):
            warnings.append({"code": "invalid_provider_response_schema_contract_skipped", "path": prsc.get("artifact_path", ""), "severity": "warning"})
            continue
        src = prsc.get("source_provider_request_response_pairing_id", "")
        if src:
            provider_response_schema_contracts_by_pairing_id.setdefault(src, []).append(prsc)
        else:
            warnings.append({"code": "orphan_provider_response_schema_contract", "path": prsc.get("artifact_path", ""), "severity": "warning"})

    provider_response_review_results_by_schema_contract_id: dict[str, list[dict[str, Any]]] = {}
    for prrr in provider_response_review_result_items:
        if prrr.get("_invalid"):
            warnings.append({"code": "invalid_provider_response_review_result_skipped", "path": prrr.get("artifact_path", ""), "severity": "warning"})
            continue
        src = prrr.get("source_provider_response_schema_contract_id", "")
        if src:
            provider_response_review_results_by_schema_contract_id.setdefault(src, []).append(prrr)
        else:
            warnings.append({"code": "orphan_provider_response_review_result", "path": prrr.get("artifact_path", ""), "severity": "warning"})

    provider_execution_unlock_states_by_review_result_id: dict[str, list[dict[str, Any]]] = {}
    for pues in provider_execution_unlock_state_items:
        if pues.get("_invalid"):
            warnings.append({"code": "invalid_provider_execution_unlock_state_skipped", "path": pues.get("artifact_path", ""), "severity": "warning"})
            continue
        src = pues.get("source_provider_response_review_result_id", "")
        if src:
            provider_execution_unlock_states_by_review_result_id.setdefault(src, []).append(pues)
        else:
            warnings.append({"code": "orphan_provider_execution_unlock_state", "path": pues.get("artifact_path", ""), "severity": "warning"})

    provider_adapter_interface_contracts_by_unlock_state_id: dict[str, list[dict[str, Any]]] = {}
    provider_adapter_interface_contracts_by_review_result_id: dict[str, list[dict[str, Any]]] = {}
    for paic in provider_adapter_interface_contract_items:
        if paic.get("_invalid"):
            warnings.append({"code": "invalid_provider_adapter_interface_contract_skipped", "path": paic.get("artifact_path", ""), "severity": "warning"})
            continue
        src_us = paic.get("source_provider_execution_unlock_state_id", "")
        if src_us:
            provider_adapter_interface_contracts_by_unlock_state_id.setdefault(src_us, []).append(paic)
        src_rr = paic.get("source_provider_response_review_result_id", "")
        if src_rr:
            provider_adapter_interface_contracts_by_review_result_id.setdefault(src_rr, []).append(paic)
        if not src_us and not src_rr:
            warnings.append({"code": "orphan_provider_adapter_interface_contract", "path": paic.get("artifact_path", ""), "severity": "warning"})

    provider_mock_response_simulations_by_adapter_contract_id: dict[str, list[dict[str, Any]]] = {}
    for pmrs in provider_mock_response_simulation_items:
        if pmrs.get("_invalid"):
            warnings.append({"code": "invalid_provider_mock_response_simulation_skipped", "path": pmrs.get("artifact_path", ""), "severity": "warning"})
            continue
        src_ac = pmrs.get("source_provider_adapter_interface_contract_id", "")
        if src_ac:
            provider_mock_response_simulations_by_adapter_contract_id.setdefault(src_ac, []).append(pmrs)
        else:
            warnings.append({"code": "orphan_provider_mock_response_simulation", "path": pmrs.get("artifact_path", ""), "severity": "warning"})

    provider_mock_response_import_candidates_by_simulation_id: dict[str, list[dict[str, Any]]] = {}
    for pmrc in provider_mock_response_import_candidate_items:
        if pmrc.get("_invalid"):
            warnings.append({"code": "invalid_provider_mock_response_import_candidate_skipped", "path": pmrc.get("artifact_path", ""), "severity": "warning"})
            continue
        src_ms = pmrc.get("source_provider_mock_response_simulation_id", "")
        if src_ms:
            provider_mock_response_import_candidates_by_simulation_id.setdefault(src_ms, []).append(pmrc)
        else:
            warnings.append({"code": "orphan_provider_mock_response_import_candidate", "path": pmrc.get("artifact_path", ""), "severity": "warning"})

    from atlas_agent.research.provider_mock_response_review_sandbox import iter_provider_mock_response_review_sandbox_artifacts
    provider_mock_response_review_sandbox_items = iter_provider_mock_response_review_sandbox_artifacts(workspace_path, symbol=symbol_filter)

    provider_mock_response_review_sandboxes_by_import_candidate_id: dict[str, list[dict[str, Any]]] = {}
    for pmrsb in provider_mock_response_review_sandbox_items:
        if pmrsb.get("_invalid"):
            warnings.append({"code": "invalid_provider_mock_response_review_sandbox_skipped", "path": pmrsb.get("artifact_path", ""), "severity": "warning"})
            continue
        src_ic = pmrsb.get("source_provider_mock_response_import_candidate_id", "")
        if src_ic:
            provider_mock_response_review_sandboxes_by_import_candidate_id.setdefault(src_ic, []).append(pmrsb)
        else:
            warnings.append({"code": "orphan_provider_mock_response_review_sandbox", "path": pmrsb.get("artifact_path", ""), "severity": "warning"})

    from atlas_agent.research.provider_mock_response_trust_decision_blocker import iter_provider_mock_response_trust_decision_blocker_artifacts
    provider_mock_response_trust_decision_blocker_items = iter_provider_mock_response_trust_decision_blocker_artifacts(workspace_path, symbol=symbol_filter)

    provider_mock_response_trust_decision_blockers_by_review_sandbox_id: dict[str, list[dict[str, Any]]] = {}
    for pmtb in provider_mock_response_trust_decision_blocker_items:
        if pmtb.get("_invalid"):
            warnings.append({"code": "invalid_provider_mock_response_trust_decision_blocker_skipped", "path": pmtb.get("artifact_path", ""), "severity": "warning"})
            continue
        src_rs = pmtb.get("source_provider_mock_response_review_sandbox_id", "")
        if src_rs:
            provider_mock_response_trust_decision_blockers_by_review_sandbox_id.setdefault(src_rs, []).append(pmtb)
        else:
            warnings.append({"code": "orphan_provider_mock_response_trust_decision_blocker", "path": pmtb.get("artifact_path", ""), "severity": "warning"})

    from atlas_agent.research.provider_mock_response_final_safety_seal import iter_provider_mock_response_final_safety_seal_artifacts
    provider_mock_response_final_safety_seal_items = iter_provider_mock_response_final_safety_seal_artifacts(workspace_path, symbol=symbol_filter)

    provider_mock_response_final_safety_seals_by_trust_decision_blocker_id: dict[str, list[dict[str, Any]]] = {}
    for pmfs in provider_mock_response_final_safety_seal_items:
        if pmfs.get("_invalid"):
            warnings.append({"code": "invalid_provider_mock_response_final_safety_seal_skipped", "path": pmfs.get("artifact_path", ""), "severity": "warning"})
            continue
        src_tb = pmfs.get("source_trust_decision_blocker_id", "")
        if src_tb:
            provider_mock_response_final_safety_seals_by_trust_decision_blocker_id.setdefault(src_tb, []).append(pmfs)
        else:
            warnings.append({"code": "orphan_provider_mock_response_final_safety_seal", "path": pmfs.get("artifact_path", ""), "severity": "warning"})

    # Track seen plan IDs to detect orphans (plans whose source_run_id has no research artifact)
    seen_run_ids = set()
    for r in research_items:
        if not r.get("_malformed"):
            seen_run_ids.add(r["run_id"])

    for plan in plan_items:
        if plan.get("_malformed"):
            continue
        src = plan.get("source_run_id", "")
        if src and src not in seen_run_ids:
            warnings.append({"code": "orphan_plan", "path": plan.get("artifact_path", ""), "severity": "warning"})

    # Track seen plan IDs for orphan verification/evaluation detection
    seen_plan_ids = set()
    for plan in plan_items:
        if not plan.get("_malformed"):
            seen_plan_ids.add(plan.get("plan_id", ""))

    for v in verification_items:
        src = v.get("source_plan_id", "")
        if src and src not in seen_plan_ids:
            warnings.append({"code": "orphan_verification", "path": v.get("artifact_path", ""), "severity": "warning"})

    for e in evaluation_items:
        src = e.get("source_plan_id", "")
        if src and src not in seen_plan_ids:
            warnings.append({"code": "orphan_evaluation", "path": e.get("artifact_path", ""), "severity": "warning"})

    # Track seen prompt IDs for orphan provider response detection
    seen_prompt_ids = set()
    for p in prompt_items:
        seen_prompt_ids.add(p.get("prompt_packet_id", ""))

    for pr in provider_response_items:
        src = pr.get("source_prompt_packet_id", "")
        if src and src not in seen_prompt_ids:
            warnings.append({"code": "orphan_provider_response", "path": pr.get("artifact_path", ""), "severity": "warning"})

    # Track seen provider response IDs for orphan response review detection
    seen_provider_response_ids = set()
    for pr in provider_response_items:
        seen_provider_response_ids.add(pr.get("provider_response_id", ""))

    for rr in response_review_items:
        src = rr.get("source_provider_response_id", "")
        if src and src not in seen_provider_response_ids:
            warnings.append({"code": "orphan_response_review", "path": rr.get("artifact_path", ""), "severity": "warning"})

    # Index dossiers by source_run_id
    dossiers_by_run_id: dict[str, list[dict[str, Any]]] = {}
    for d in dossier_items:
        src = d.get("source_run_id", "")
        if src:
            dossiers_by_run_id.setdefault(src, []).append(d)
        else:
            warnings.append({"code": "orphan_dossier", "path": d.get("artifact_path", ""), "severity": "warning"})

    # Track seen run IDs for orphan prompt detection
    for p in prompt_items:
        src = p.get("source_run_id", "")
        if src and src not in seen_run_ids:
            warnings.append({"code": "orphan_prompt", "path": p.get("artifact_path", ""), "severity": "warning"})

    # Track seen provider execution state IDs for orphan audit packet detection
    seen_state_ids = set()
    for pes in provider_execution_state_items:
        seen_state_ids.add(pes.get("provider_execution_state_id", ""))

    for peap in provider_execution_audit_packet_items:
        src = peap.get("source_provider_execution_state_id", "")
        if src and src not in seen_state_ids:
            warnings.append({"code": "orphan_provider_execution_audit_packet", "path": peap.get("artifact_path", ""), "severity": "warning"})

    # Track seen audit packet IDs for orphan readiness report detection
    seen_audit_packet_ids = set()
    for peap in provider_execution_audit_packet_items:
        if not peap.get("_invalid"):
            seen_audit_packet_ids.add(peap.get("provider_execution_audit_packet_id", ""))

    for perr in provider_execution_readiness_report_items:
        src = perr.get("source_provider_execution_audit_packet_id", "")
        if src and src not in seen_audit_packet_ids:
            warnings.append({"code": "orphan_provider_execution_readiness_report", "path": perr.get("artifact_path", ""), "severity": "warning"})

    # Track seen readiness report IDs for orphan freeze detection
    seen_readiness_report_ids = set()
    for perr in provider_execution_readiness_report_items:
        if not perr.get("_invalid"):
            seen_readiness_report_ids.add(perr.get("provider_execution_readiness_report_id", ""))

    for ppf in provider_preflight_freeze_items:
        src = ppf.get("source_provider_execution_readiness_report_id", "")
        if src and src not in seen_readiness_report_ids:
            warnings.append({"code": "orphan_provider_preflight_freeze", "path": ppf.get("artifact_path", ""), "severity": "warning"})

    # Track seen freeze IDs for orphan opt-in policy detection
    seen_freeze_ids = set()
    for ppf in provider_preflight_freeze_items:
        if not ppf.get("_invalid"):
            seen_freeze_ids.add(ppf.get("provider_preflight_freeze_id", ""))

    for pop in provider_opt_in_policy_items:
        src = pop.get("source_provider_preflight_freeze_id", "")
        if src and src not in seen_freeze_ids:
            warnings.append({"code": "orphan_provider_opt_in_policy", "path": pop.get("artifact_path", ""), "severity": "warning"})

    # Track seen policy IDs for orphan credential boundary detection
    seen_policy_ids = set()
    for pop in provider_opt_in_policy_items:
        if not pop.get("_invalid"):
            seen_policy_ids.add(pop.get("provider_opt_in_policy_id", ""))

    for pcb in provider_credential_boundary_items:
        src = pcb.get("source_provider_opt_in_policy_id", "")
        if src and src not in seen_policy_ids:
            warnings.append({"code": "orphan_provider_credential_boundary", "path": pcb.get("artifact_path", ""), "severity": "warning"})

    # Track seen credential boundary IDs for orphan payload preview detection
    seen_boundary_ids = set()
    for pcb in provider_credential_boundary_items:
        if not pcb.get("_invalid"):
            seen_boundary_ids.add(pcb.get("provider_credential_boundary_id", ""))

    for pp in provider_outbound_payload_preview_items:
        src = pp.get("source_provider_credential_boundary_id", "")
        if src and src not in seen_boundary_ids:
            warnings.append({"code": "orphan_provider_outbound_payload_preview", "path": pp.get("artifact_path", ""), "severity": "warning"})

    # Track seen payload preview IDs for orphan intake policy detection
    seen_payload_preview_ids = set()
    for pp in provider_outbound_payload_preview_items:
        if not pp.get("_invalid"):
            seen_payload_preview_ids.add(pp.get("provider_outbound_payload_preview_id", ""))

    for pip in provider_response_intake_policy_items:
        src = pip.get("source_provider_outbound_payload_preview_id", "")
        if src and src not in seen_payload_preview_ids:
            warnings.append({"code": "orphan_provider_response_intake_policy", "path": pip.get("artifact_path", ""), "severity": "warning"})

    # Track seen intake policy IDs for orphan pairing detection
    seen_intake_policy_ids = set()
    for pip in provider_response_intake_policy_items:
        if not pip.get("_invalid"):
            seen_intake_policy_ids.add(pip.get("provider_response_intake_policy_id", ""))

    for prrp in provider_request_response_pairing_items:
        src = prrp.get("source_provider_response_intake_policy_id", "")
        if src and src not in seen_intake_policy_ids:
            warnings.append({"code": "orphan_provider_request_response_pairing", "path": prrp.get("artifact_path", ""), "severity": "warning"})

    # Track seen pairing IDs for orphan schema contract detection
    seen_pairing_ids = set()
    for prrp in provider_request_response_pairing_items:
        if not prrp.get("_invalid"):
            seen_pairing_ids.add(prrp.get("provider_request_response_pairing_id", ""))

    for prsc in provider_response_schema_contract_items:
        src = prsc.get("source_provider_request_response_pairing_id", "")
        if src and src not in seen_pairing_ids:
            warnings.append({"code": "orphan_provider_response_schema_contract", "path": prsc.get("artifact_path", ""), "severity": "warning"})

    # Track seen schema contract IDs for orphan provider response review result detection
    seen_schema_contract_ids = set()
    for prsc in provider_response_schema_contract_items:
        if not prsc.get("_invalid"):
            seen_schema_contract_ids.add(prsc.get("provider_response_schema_contract_id", ""))

    for prrr in provider_response_review_result_items:
        src = prrr.get("source_provider_response_schema_contract_id", "")
        if src and src not in seen_schema_contract_ids:
            warnings.append({"code": "orphan_provider_response_review_result", "path": prrr.get("artifact_path", ""), "severity": "warning"})

    # Track seen review result IDs for orphan unlock state detection
    seen_review_result_ids = set()
    for prrr in provider_response_review_result_items:
        if not prrr.get("_invalid"):
            seen_review_result_ids.add(prrr.get("provider_response_review_result_id", ""))

    for pues in provider_execution_unlock_state_items:
        src = pues.get("source_provider_response_review_result_id", "")
        if src and src not in seen_review_result_ids:
            warnings.append({"code": "orphan_provider_execution_unlock_state", "path": pues.get("artifact_path", ""), "severity": "warning"})

    def _timeline_summary(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
        """Build an acyclic JSON-safe summary from an artifact index item."""
        summary: dict[str, Any] = {}
        for field in fields:
            if field not in item:
                continue
            value = item.get(field)
            if value is None:
                continue
            elif isinstance(value, (str, int, float, bool)):
                summary[field] = value
            else:
                summary[field] = str(value)[:200]
        return summary

    # Build entries
    entries: list[dict[str, Any]] = []
    for research in research_items:
        if research.get("_malformed"):
            continue
        run_id = research["run_id"]

        if run_id_filter is not None and run_id != run_id_filter:
            continue

        plans: list[dict[str, Any]] = []
        for plan in plans_by_run_id.get(run_id, []):
            plan_id = plan.get("plan_id", "")
            verifications = [
                {
                    "verification_id": v.get("verification_id", ""),
                    "recommendation": v.get("recommendation", ""),
                    "artifact_path": v.get("artifact_path", ""),
                }
                for v in verifications_by_plan_id.get(plan_id, [])
            ]
            evaluations = [
                {
                    "evaluation_id": e.get("evaluation_id", ""),
                    "recommendation": e.get("recommendation", ""),
                    "artifact_path": e.get("artifact_path", ""),
                }
                for e in evaluations_by_plan_id.get(plan_id, [])
            ]
            plans.append(
                {
                    "plan_id": plan_id,
                    "created_at": plan.get("created_at", ""),
                    "artifact_path": plan.get("artifact_path", ""),
                    "verifications": verifications,
                    "evaluations": evaluations,
                }
            )

        prompts: list[dict[str, Any]] = []
        for prompt in prompts_by_run_id.get(run_id, []):
            prompt_id = prompt.get("prompt_packet_id", "")
            provider_responses = []
            for pr in provider_responses_by_prompt_id.get(prompt_id, []):
                pr_id = pr.get("provider_response_id", "")
                response_reviews = [
                    {
                        "response_review_id": rr.get("response_review_id", ""),
                        "recommendation": rr.get("recommendation", ""),
                        "artifact_path": rr.get("artifact_path", ""),
                    }
                    for rr in response_reviews_by_provider_id.get(pr_id, [])
                ]
                provider_responses.append({
                    "provider_response_id": pr_id,
                    "provider": pr.get("provider", "unknown"),
                    "recommendation": pr.get("recommendation", ""),
                    "artifact_path": pr.get("artifact_path", ""),
                    "response_reviews": response_reviews,
                })
            sandbox_requests = []
            for sr in sandbox_requests_by_prompt_id.get(prompt_id, []):
                sr_id = sr.get("sandbox_request_id", "")
                sr_copy = _timeline_summary(sr, (
                    "sandbox_request_id",
                    "prompt_packet_id",
                    "source_run_id",
                    "symbol",
                    "artifact_path",
                    "provider",
                    "created_at",
                ))
                pcp_list = provider_call_plans_by_sandbox_id.get(sr_id, [])
                pcp_with_dry_runs = []
                for pcp in pcp_list:
                    pcp_copy = _timeline_summary(pcp, (
                        "provider_call_plan_id",
                        "source_sandbox_request_id",
                        "source_run_id",
                        "symbol",
                        "artifact_path",
                        "provider_id",
                        "model_id",
                        "created_at",
                        "execution_mode",
                        "provider_call_allowed",
                    ))
                    pcp_id = pcp_copy.get("provider_call_plan_id", "")
                    dry_runs = provider_execution_dry_runs_by_plan_id.get(pcp_id, [])
                    dry_runs_with_states = []
                    for dr in dry_runs:
                        dr_copy = _timeline_summary(dr, (
                            "provider_execution_dry_run_id",
                            "source_provider_call_plan_id",
                            "source_run_id",
                            "symbol",
                            "artifact_path",
                            "provider_id",
                            "model_id",
                            "created_at",
                            "execution_mode",
                        ))
                        dr_id = dr_copy.get("provider_execution_dry_run_id", "")
                        states = provider_execution_states_by_dry_run_id.get(dr_id, [])
                        states_with_audit_packets = []
                        for state in states:
                            state_copy = _timeline_summary(state, (
                                "provider_execution_state_id",
                                "source_provider_execution_dry_run_id",
                                "source_run_id",
                                "symbol",
                                "artifact_path",
                                "provider_id",
                                "model_id",
                                "created_at",
                                "state",
                                "provider_call_allowed",
                                "actual_provider_call_made",
                            ))
                            state_id = state_copy.get("provider_execution_state_id", "")
                            audit_packets = provider_execution_audit_packets_by_state_id.get(state_id, [])
                            audit_packets_with_readiness = []
                            for ap in audit_packets:
                                ap_copy = _timeline_summary(ap, (
                                    "provider_execution_audit_packet_id",
                                    "source_provider_execution_state_id",
                                    "source_run_id",
                                    "symbol",
                                    "artifact_path",
                                    "provider_id",
                                    "model_id",
                                    "created_at",
                                    "audit_status",
                                    "execution_status",
                                    "provider_call_allowed",
                                    "actual_provider_call_made",
                                    "broker_touched",
                                ))
                                ap_id = ap_copy.get("provider_execution_audit_packet_id", "")
                                readiness_reports = provider_execution_readiness_reports_by_audit_id.get(ap_id, [])
                                readiness_reports_with_freezes = []
                                for rpt in readiness_reports:
                                    rpt_copy = _timeline_summary(rpt, (
                                        "provider_execution_readiness_report_id",
                                        "source_provider_execution_audit_packet_id",
                                        "source_run_id",
                                        "symbol",
                                        "artifact_path",
                                        "provider_id",
                                        "model_id",
                                        "created_at",
                                        "readiness_status",
                                        "readiness_score",
                                        "chain_health",
                                        "provider_call_allowed",
                                        "actual_provider_call_made",
                                    ))
                                    rpt_id = rpt_copy.get("provider_execution_readiness_report_id", "")
                                    freezes = provider_preflight_freezes_by_readiness_id.get(rpt_id, [])
                                    freezes_with_policies = []
                                    for freeze in freezes:
                                        freeze_copy = _timeline_summary(freeze, (
                                            "provider_preflight_freeze_id",
                                            "source_provider_execution_readiness_report_id",
                                            "source_run_id",
                                            "symbol",
                                            "artifact_path",
                                            "provider_id",
                                            "model_id",
                                            "created_at",
                                            "freeze_status",
                                            "freeze_scope",
                                            "freeze_recommendation",
                                            "provider_call_allowed",
                                            "actual_provider_call_made",
                                        ))
                                        freeze_id = freeze_copy.get("provider_preflight_freeze_id", "")
                                        policies_with_boundaries = []
                                        for policy in provider_opt_in_policies_by_freeze_id.get(freeze_id, []):
                                            policy_copy = _timeline_summary(policy, (
                                                "provider_opt_in_policy_id",
                                                "source_provider_preflight_freeze_id",
                                                "source_run_id",
                                                "symbol",
                                                "artifact_path",
                                                "provider_id",
                                                "model_id",
                                                "created_at",
                                                "policy_status",
                                                "policy_scope",
                                                "opt_in_state",
                                                "provider_call_allowed",
                                                "actual_provider_call_made",
                                            ))
                                            policy_id = policy_copy.get("provider_opt_in_policy_id", "")
                                            boundaries = provider_credential_boundaries_by_policy_id.get(policy_id, [])
                                            boundaries_with_previews = []
                                            for boundary in boundaries:
                                                boundary_copy = _timeline_summary(boundary, (
                                                    "provider_credential_boundary_id",
                                                    "source_provider_opt_in_policy_id",
                                                    "source_run_id",
                                                    "symbol",
                                                    "artifact_path",
                                                    "provider_id",
                                                    "model_id",
                                                    "created_at",
                                                    "credential_boundary_status",
                                                    "credentials_loaded",
                                                    "env_read_attempted",
                                                    "dotenv_loaded",
                                                    "provider_call_allowed",
                                                    "actual_provider_call_made",
                                                ))
                                                boundary_id = boundary_copy.get("provider_credential_boundary_id", "")
                                                previews = provider_outbound_payload_previews_by_boundary_id.get(boundary_id, [])
                                                previews_with_policies = []
                                                for preview in previews:
                                                    preview_copy = _timeline_summary(preview, (
                                                        "provider_outbound_payload_preview_id",
                                                        "source_provider_credential_boundary_id",
                                                        "source_run_id",
                                                        "symbol",
                                                        "artifact_path",
                                                        "provider_id",
                                                        "model_id",
                                                        "created_at",
                                                        "payload_preview_status",
                                                        "payload_preview_scope",
                                                        "payload_body_stored",
                                                        "raw_prompt_stored",
                                                        "raw_provider_request_stored",
                                                        "outbound_request_sent",
                                                        "provider_call_allowed",
                                                        "actual_provider_call_made",
                                                    ))
                                                    preview_id = preview_copy.get("provider_outbound_payload_preview_id", "")
                                                    policies = provider_response_intake_policies_by_preview_id.get(preview_id, [])
                                                    policies_with_pairings = []
                                                    for intake_policy in policies:
                                                        intake_policy_copy = _timeline_summary(intake_policy, (
                                                            "provider_response_intake_policy_id",
                                                            "source_provider_outbound_payload_preview_id",
                                                            "source_run_id",
                                                            "symbol",
                                                            "artifact_path",
                                                            "provider_id",
                                                            "model_id",
                                                            "created_at",
                                                            "response_intake_policy_status",
                                                            "response_intake_policy_scope",
                                                            "provider_response_received",
                                                            "provider_response_trusted",
                                                            "provider_response_can_create_orders",
                                                            "provider_response_can_approve_orders",
                                                            "provider_response_can_call_broker",
                                                            "provider_call_allowed",
                                                            "actual_provider_call_made",
                                                        ))
                                                        intake_policy_id = intake_policy_copy.get("provider_response_intake_policy_id", "")
                                                        pairing_summaries = []
                                                        for pairing in provider_request_response_pairings_by_intake_policy_id.get(intake_policy_id, []):
                                                            pairing_copy = _timeline_summary(pairing, (
                                                                "provider_request_response_pairing_id",
                                                                "source_provider_response_intake_policy_id",
                                                                "source_provider_outbound_payload_preview_id",
                                                                "source_provider_credential_boundary_id",
                                                                "source_provider_opt_in_policy_id",
                                                                "source_provider_preflight_freeze_id",
                                                                "source_provider_execution_readiness_report_id",
                                                                "source_provider_execution_audit_packet_id",
                                                                "source_provider_execution_state_id",
                                                                "source_provider_execution_dry_run_id",
                                                                "source_provider_call_plan_id",
                                                                "source_sandbox_request_id",
                                                                "source_prompt_packet_id",
                                                                "source_run_id",
                                                                "symbol",
                                                                "artifact_path",
                                                                "provider_id",
                                                                "model_id",
                                                                "created_at",
                                                                "pairing_status",
                                                                "pairing_state",
                                                                "request_response_pair_completed",
                                                                "future_response_artifact_present",
                                                                "future_response_hash_present",
                                                                "provider_trace_id_present",
                                                                "external_correlation_id_present",
                                                                "raw_request_body_stored",
                                                                "raw_response_body_stored",
                                                                "provider_response_received",
                                                                "provider_response_trusted",
                                                                "provider_response_imported",
                                                                "provider_response_reviewed",
                                                                "provider_response_can_create_orders",
                                                                "provider_response_can_approve_orders",
                                                                "provider_response_can_call_broker",
                                                                "provider_call_allowed",
                                                                "actual_provider_call_made",
                                                                "outbound_request_sent",
                                                                "trading_signal_generated",
                                                                "approval_created",
                                                                "pending_order_created",
                                                                "broker_touched",
                                                            ))
                                                            pairing_id = pairing_copy.get("provider_request_response_pairing_id", "")
                                                            contract_summaries = []
                                                            for contract in provider_response_schema_contracts_by_pairing_id.get(pairing_id, []):
                                                                contract_summary = _timeline_summary(contract, (
                                                                    "provider_response_schema_contract_id",
                                                                    "source_provider_request_response_pairing_id",
                                                                    "source_provider_response_intake_policy_id",
                                                                    "source_provider_outbound_payload_preview_id",
                                                                    "source_provider_credential_boundary_id",
                                                                    "source_provider_opt_in_policy_id",
                                                                    "source_provider_preflight_freeze_id",
                                                                    "source_provider_execution_readiness_report_id",
                                                                    "source_provider_execution_audit_packet_id",
                                                                    "source_provider_execution_state_id",
                                                                    "source_provider_execution_dry_run_id",
                                                                    "source_provider_call_plan_id",
                                                                    "source_sandbox_request_id",
                                                                    "source_prompt_packet_id",
                                                                    "source_run_id",
                                                                    "symbol",
                                                                    "artifact_path",
                                                                    "provider_id",
                                                                    "model_id",
                                                                    "created_at",
                                                                    "response_schema_status",
                                                                    "response_schema_scope",
                                                                    "response_schema_state",
                                                                    "schema_contract_enabled",
                                                                    "manual_review_gate_open",
                                                                    "automatic_review_allowed",
                                                                    "future_response_artifact_present",
                                                                    "future_response_schema_validated",
                                                                    "provider_response_received",
                                                                    "provider_response_trusted",
                                                                    "provider_response_can_create_orders",
                                                                    "provider_response_can_approve_orders",
                                                                    "provider_response_can_call_broker",
                                                                    "response_schema_allows_trading_signal",
                                                                    "response_schema_allows_order_creation",
                                                                    "response_schema_allows_order_approval",
                                                                    "response_schema_allows_broker_call",
                                                                    "raw_response_body_stored",
                                                                    "raw_prompt_body_stored",
                                                                    "provider_call_allowed",
                                                                    "actual_provider_call_made",
                                                                    "outbound_request_sent",
                                                                    "trading_signal_generated",
                                                                    "approval_created",
                                                                    "pending_order_created",
                                                                    "broker_touched",
                                                                ))
                                                                contract_id = contract_summary.get("provider_response_schema_contract_id", "")
                                                                contract_summary["provider_response_review_results"] = [
                                                                    _timeline_summary(review_result, (
                                                                        "provider_response_review_result_id",
                                                                        "source_provider_response_schema_contract_id",
                                                                        "source_provider_request_response_pairing_id",
                                                                        "source_provider_response_intake_policy_id",
                                                                        "source_provider_outbound_payload_preview_id",
                                                                        "symbol",
                                                                        "artifact_path",
                                                                        "provider_id",
                                                                        "model_id",
                                                                        "created_at",
                                                                        "review_result_status",
                                                                        "review_result_state",
                                                                        "review_decision",
                                                                        "provider_call_allowed",
                                                                        "actual_provider_call_made",
                                                                    ))
                                                                    for review_result in provider_response_review_results_by_schema_contract_id.get(contract_id, [])
                                                                ]
                                                                for review_result in contract_summary.get("provider_response_review_results", []):
                                                                    rr_id = review_result.get("provider_response_review_result_id", "")
                                                                    review_result["provider_execution_unlock_states"] = [
                                                                        _timeline_summary(unlock_state, (
                                                                            "provider_execution_unlock_state_id",
                                                                            "source_provider_response_review_result_id",
                                                                            "source_provider_response_schema_contract_id",
                                                                            "source_provider_request_response_pairing_id",
                                                                            "source_provider_response_intake_policy_id",
                                                                            "source_provider_outbound_payload_preview_id",
                                                                            "symbol",
                                                                            "artifact_path",
                                                                            "provider_id",
                                                                            "model_id",
                                                                            "created_at",
                                                                            "unlock_state_status",
                                                                            "unlock_state",
                                                                            "current_state",
                                                                            "provider_execution_unlocked",
                                                                            "provider_call_allowed",
                                                                            "manual_unlock_granted",
                                                                        ))
                                                                        for unlock_state in provider_execution_unlock_states_by_review_result_id.get(rr_id, [])
                                                                    ]
                                                                    review_result["provider_adapter_interface_contracts"] = []
                                                                    for contract in provider_adapter_interface_contracts_by_review_result_id.get(rr_id, []):
                                                                        contract_copy = _timeline_summary(contract, (
                                                                            "provider_adapter_interface_contract_id",
                                                                            "source_provider_execution_unlock_state_id",
                                                                            "source_provider_response_review_result_id",
                                                                            "source_provider_response_schema_contract_id",
                                                                            "source_provider_request_response_pairing_id",
                                                                            "source_provider_response_intake_policy_id",
                                                                            "source_provider_outbound_payload_preview_id",
                                                                            "symbol",
                                                                            "artifact_path",
                                                                            "provider_id",
                                                                            "model_id",
                                                                            "created_at",
                                                                            "adapter_contract_status",
                                                                            "adapter_state",
                                                                            "adapter_interface_recorded",
                                                                            "disabled_adapter_available",
                                                                            "adapter_present",
                                                                            "adapter_enabled",
                                                                            "real_provider_adapter_implemented",
                                                                            "provider_sdk_imported",
                                                                            "http_client_imported",
                                                                            "network_enabled",
                                                                            "credentials_loaded",
                                                                            "provider_call_allowed",
                                                                            "actual_provider_call_made",
                                                                            "outbound_request_sent",
                                                                            "provider_response_received",
                                                                            "provider_response_trusted",
                                                                            "trust_upgrade_performed",
                                                                            "trading_signal_generated",
                                                                            "approval_created",
                                                                            "pending_order_created",
                                                                            "broker_touched",
                                                                        ))
                                                                        ac_id = contract_copy.get("provider_adapter_interface_contract_id", "")
                                                                        contract_copy["provider_mock_response_simulations"] = [
                                                                            _timeline_summary(pmrs, (
                                                                                "provider_mock_response_simulation_id",
                                                                                "source_provider_adapter_interface_contract_id",
                                                                                "source_run_id",
                                                                                "symbol",
                                                                                "artifact_path",
                                                                                "provider_id",
                                                                                "model_id",
                                                                                "created_at",
                                                                                "mock_simulation_status",
                                                                                "mock_simulation_scope",
                                                                                "mock_simulation_state",
                                                                                "mock_adapter_used",
                                                                                "mock_response_simulated",
                                                                                "mock_only",
                                                                                "real_provider_request_sent",
                                                                                "real_provider_response_received",
                                                                                "provider_response_trusted",
                                                                                "provider_call_allowed",
                                                                                "broker_touched",
                                                                            ))
                                                                            for pmrs in provider_mock_response_simulations_by_adapter_contract_id.get(ac_id, [])
                                                                        ]
                                                                        contract_copy["provider_mock_response_import_candidates"] = [
                                                                            _timeline_summary(pmrc, (
                                                                                "provider_mock_response_import_candidate_id",
                                                                                "source_provider_mock_response_simulation_id",
                                                                                "source_run_id",
                                                                                "symbol",
                                                                                "artifact_path",
                                                                                "provider_id",
                                                                                "model_id",
                                                                                "created_at",
                                                                                "mock_import_candidate_status",
                                                                                "mock_import_candidate_scope",
                                                                                "mock_import_candidate_state",
                                                                                "mock_response_import_candidate_recorded",
                                                                                "mock_response_source_verified",
                                                                                "mock_schema_candidate_checked",
                                                                                "mock_schema_candidate_valid",
                                                                                "mock_only",
                                                                                "real_provider_response_imported",
                                                                                "provider_response_trusted",
                                                                                "provider_call_allowed",
                                                                                "broker_touched",
                                                                            ))
                                                                            for pmrs in provider_mock_response_simulations_by_adapter_contract_id.get(ac_id, [])
                                                                            for pmrc in provider_mock_response_import_candidates_by_simulation_id.get(
                                                                                pmrs.get("provider_mock_response_simulation_id", ""), [])
                                                                        ]
                                                                        for pmrc in contract_copy["provider_mock_response_import_candidates"]:
                                                                            pmrc_id = pmrc.get("provider_mock_response_import_candidate_id", "")
                                                                            pmrc["provider_mock_response_review_sandboxes"] = []
                                                                            for pmrsb in provider_mock_response_review_sandboxes_by_import_candidate_id.get(pmrc_id, []):
                                                                                rsb_summary = _timeline_summary(pmrsb, (
                                                                                    "provider_mock_response_review_sandbox_id",
                                                                                    "source_provider_mock_response_import_candidate_id",
                                                                                    "source_run_id",
                                                                                    "symbol",
                                                                                    "artifact_path",
                                                                                    "provider_id",
                                                                                    "model_id",
                                                                                    "created_at",
                                                                                    "mock_review_sandbox_status",
                                                                                    "mock_review_sandbox_scope",
                                                                                    "mock_review_sandbox_state",
                                                                                    "mock_review_sandbox_recorded",
                                                                                    "mock_review_source_verified",
                                                                                    "mock_review_checks_completed",
                                                                                    "mock_review_passed",
                                                                                    "mock_only",
                                                                                    "sandbox_review_only",
                                                                                    "real_provider_response_reviewed",
                                                                                    "provider_response_trusted",
                                                                                    "provider_call_allowed",
                                                                                    "broker_touched",
                                                                                ))
                                                                                rsb_id = rsb_summary.get("provider_mock_response_review_sandbox_id", "")
                                                                                trust_blocker_summaries = []
                                                                                for pmtb in provider_mock_response_trust_decision_blockers_by_review_sandbox_id.get(rsb_id, []):
                                                                                    pmtb_summary = _timeline_summary(pmtb, (
                                                                                        "provider_mock_response_trust_decision_blocker_id",
                                                                                        "source_provider_mock_response_review_sandbox_id",
                                                                                        "source_run_id",
                                                                                        "symbol",
                                                                                        "artifact_path",
                                                                                        "provider_id",
                                                                                        "model_id",
                                                                                        "created_at",
                                                                                        "trust_decision_blocker_status",
                                                                                        "trust_decision_blocker_scope",
                                                                                        "trust_decision_blocker_state",
                                                                                        "trust_decision_blocker_recorded",
                                                                                        "trust_source_verified",
                                                                                        "trust_blocker_active",
                                                                                        "trust_decision_required",
                                                                                        "trust_decision_present",
                                                                                        "trust_decision_granted",
                                                                                        "trust_decision_explicitly_blocked",
                                                                                        "trust_upgrade_performed",
                                                                                        "provider_response_trusted",
                                                                                        "mock_response_trusted",
                                                                                        "provider_call_allowed",
                                                                                        "broker_touched",
                                                                                    ))
                                                                                    pmtb_id = pmtb_summary.get("provider_mock_response_trust_decision_blocker_id", "")
                                                                                    pmtb_summary["provider_mock_response_final_safety_seals"] = [
                                                                                        _timeline_summary(pmfs, (
                                                                                            "provider_mock_response_final_safety_seal_id",
                                                                                            "source_trust_decision_blocker_id",
                                                                                            "source_run_id",
                                                                                            "symbol",
                                                                                            "artifact_path",
                                                                                            "provider_id",
                                                                                            "model_id",
                                                                                            "created_at",
                                                                                            "final_safety_seal_status",
                                                                                            "final_safety_seal_state",
                                                                                            "final_safety_seal_created",
                                                                                            "mock_pipeline_complete",
                                                                                            "seal_type",
                                                                                            "sandbox_only",
                                                                                            "no_provider_response_imported",
                                                                                            "no_real_provider_response",
                                                                                            "no_trust_granted",
                                                                                            "no_execution_unlocked",
                                                                                            "no_broker_touched",
                                                                                            "no_trading_signal_generated",
                                                                                            "no_approval_created",
                                                                                            "no_pending_order_created",
                                                                                            "provider_call_allowed",
                                                                                            "broker_touched",
                                                                                        ))
                                                                                        for pmfs in provider_mock_response_final_safety_seals_by_trust_decision_blocker_id.get(pmtb_id, [])
                                                                                    ]
                                                                                    trust_blocker_summaries.append(pmtb_summary)
                                                                                rsb_summary["provider_mock_response_trust_decision_blockers"] = trust_blocker_summaries
                                                                                pmrc["provider_mock_response_review_sandboxes"].append(rsb_summary)
                                                                        review_result["provider_adapter_interface_contracts"].append(contract_copy)
                                                                contract_summaries.append(contract_summary)
                                                            pairing_copy["provider_response_schema_contracts"] = contract_summaries
                                                            pairing_summaries.append(pairing_copy)
                                                        intake_policy_copy["provider_request_response_pairings"] = pairing_summaries
                                                        policies_with_pairings.append(intake_policy_copy)
                                                    preview_copy["provider_response_intake_policies"] = policies_with_pairings
                                                    previews_with_policies.append(preview_copy)
                                                boundary_copy["provider_outbound_payload_previews"] = previews_with_policies
                                                boundaries_with_previews.append(boundary_copy)
                                            policy_copy["provider_credential_boundaries"] = boundaries_with_previews
                                            policies_with_boundaries.append(policy_copy)
                                        freeze_copy["provider_opt_in_policies"] = policies_with_boundaries
                                        freezes_with_policies.append(freeze_copy)
                                    rpt_copy["provider_preflight_freezes"] = freezes_with_policies
                                    readiness_reports_with_freezes.append(rpt_copy)
                                ap_copy["provider_execution_readiness_reports"] = readiness_reports_with_freezes
                                audit_packets_with_readiness.append(ap_copy)
                            state_copy["provider_execution_audit_packets"] = audit_packets_with_readiness
                            states_with_audit_packets.append(state_copy)
                        dr_copy["provider_execution_states"] = states_with_audit_packets
                        dry_runs_with_states.append(dr_copy)
                    pcp_copy["provider_execution_dry_runs"] = dry_runs_with_states
                    pcp_with_dry_runs.append(pcp_copy)
                sr_copy["provider_call_plans"] = pcp_with_dry_runs
                sandbox_requests.append(sr_copy)

            prompts.append(
                {
                    "prompt_packet_id": prompt_id,
                    "created_at": prompt.get("created_at", ""),
                    "artifact_path": prompt.get("artifact_path", ""),
                    "provider_responses": provider_responses,
                    "sandbox_requests": sandbox_requests,
                }
            )

        dossiers = [
            {
                "dossier_id": d.get("dossier_id", ""),
                "recommendation": d.get("recommendation", ""),
                "artifact_path": d.get("artifact_path", ""),
            }
            for d in dossiers_by_run_id.get(run_id, [])
        ]

        entries.append(
            {
                "run_id": run_id,
                "symbol": research.get("symbol", ""),
                "created_at": research.get("created_at", ""),
                "research_path": research.get("artifact_path", ""),
                "plans": plans,
                "prompts": prompts,
                "dossiers": dossiers,
            }
        )

    # Deduplicate warnings by code+path
    seen_warnings = set()
    deduped_warnings: list[dict[str, str]] = []
    for w in warnings:
        key = (w.get("code", ""), w.get("path", ""))
        if key not in seen_warnings:
            seen_warnings.add(key)
            deduped_warnings.append(w)

    # Apply limit
    entries = entries[:limit]

    # Release candidate readiness reports (standalone, not linked to a specific run)
    rcrs = [
        {
            "release_candidate_readiness_report_id": rcr.get("release_candidate_readiness_report_id", ""),
            "symbol": rcr.get("symbol", ""),
            "version": rcr.get("version", ""),
            "readiness_status": rcr.get("readiness_status", ""),
            "readiness_score": rcr.get("readiness_score", 0),
            "created_at": rcr.get("created_at", ""),
            "artifact_path": rcr.get("artifact_path", ""),
        }
        for rcr in release_candidate_readiness_items
        if not rcr.get("_invalid")
    ]

    return {
        "ok": True,
        "status": "research_timeline",
        "entries": entries,
        "release_candidate_readiness_reports": rcrs,
        "warnings": deduped_warnings,
    }


# ---------------------------------------------------------------------------
# Prompt packet generation
# ---------------------------------------------------------------------------

# Patterns for redacting unsafe content from prompt packet artifacts.
# These are static regexes; no env-var or API-key reading is performed.
_PROMPT_ABS_PATH_RE = re.compile(r"/Users/[^\s\"']+|/private/var/[^\s\"']+|/home/[^\s\"']+|/tmp/[^\s\"']+", re.IGNORECASE)
_PROMPT_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_PROMPT_AUTH_RE = re.compile(r"\b(Authorization|Proxy-Authorization|X-API-Key|API-Key|X-Auth-Token)\s*[:=]\s*[^\s,;]+", re.IGNORECASE)
_PROMPT_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]+\b", re.IGNORECASE)
_PROMPT_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z0-9_.-]*(?:API[_-]?KEY|API[_-]?SECRET|SECRET[_-]?KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_.-]*)"
    r"(\s*[:=]\s*)"
    r"([\"']?)"
    r"([^\s,;`\"']+)"
    r"\3",
    re.IGNORECASE,
)
_PROMPT_APCA_RE = re.compile(r"\bAPCA[A-Za-z0-9_-]*\b", re.IGNORECASE)
_PROMPT_BROKER_HOST_RE = re.compile(r"\bbroker\.example\.com\b", re.IGNORECASE)
# Standalone forbidden marker words that must be fully redacted even without surrounding context.
_PROMPT_STANDALONE_FORBIDDEN_RE = re.compile(
    r"(Authorization|Bearer|SECRET|TOKEN|PASSWORD|API_KEY|API-KEY|APIKEY)",
    re.IGNORECASE,
)


def _sanitize_prompt_text(text: str) -> tuple[str, int]:
    """Redact unsafe fragments from text. Returns (sanitized, redacted_count).

    Every unsafe match is replaced entirely with [REDACTED]; no marker name is preserved.
    """
    if not isinstance(text, str):
        return text, 0

    redacted_count = 0
    sanitized = text

    # Absolute paths
    for _ in _PROMPT_ABS_PATH_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_ABS_PATH_RE.sub("[REDACTED]", sanitized)

    # Bearer tokens
    for _ in _PROMPT_BEARER_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_BEARER_RE.sub("[REDACTED]", sanitized)

    # Auth headers
    for _ in _PROMPT_AUTH_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_AUTH_RE.sub("[REDACTED]", sanitized)

    # sk- tokens
    for _ in _PROMPT_SK_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_SK_RE.sub("[REDACTED]", sanitized)

    # Secret assignments
    for _ in _PROMPT_SECRET_ASSIGNMENT_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_SECRET_ASSIGNMENT_RE.sub("[REDACTED]", sanitized)

    # APCA
    for _ in _PROMPT_APCA_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_APCA_RE.sub("[REDACTED]", sanitized)

    # Broker host
    for _ in _PROMPT_BROKER_HOST_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_BROKER_HOST_RE.sub("[REDACTED]", sanitized)

    # Standalone forbidden marker words (no prefix/suffix preserved)
    for _ in _PROMPT_STANDALONE_FORBIDDEN_RE.finditer(sanitized):
        redacted_count += 1
    sanitized = _PROMPT_STANDALONE_FORBIDDEN_RE.sub("[REDACTED]", sanitized)

    return sanitized, redacted_count


def _sanitize_prompt_value(value: Any) -> tuple[Any, int]:
    """Recursively sanitize a value. Returns (sanitized_value, redacted_count)."""
    if isinstance(value, str):
        s, c = _sanitize_prompt_text(value)
        return s, c
    if isinstance(value, list):
        total = 0
        out: list[Any] = []
        for item in value:
            s, c = _sanitize_prompt_value(item)
            out.append(s)
            total += c
        return out, total
    if isinstance(value, dict):
        total = 0
        out: dict[str, Any] = {}
        for k, v in value.items():
            s, c = _sanitize_prompt_value(v)
            out[k] = s
            total += c
        return out, total
    return value, 0


def _truncate_user_context(
    context: dict[str, Any], max_chars: int
) -> tuple[dict[str, Any], bool]:
    """Truncate text fields so total character count <= max_chars.

    Returns (truncated_context, was_truncated).
    """
    # Flatten all string values with unique paths for proportional trimming.
    # Path is key for dict values, or (key, index) for list items.
    flat: list[tuple[str | tuple[str, int], str]] = []
    for key, val in context.items():
        if isinstance(val, str):
            flat.append((key, val))
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                if isinstance(item, str):
                    flat.append(((key, idx), item))

    total = sum(len(v) for _, v in flat)
    if total <= max_chars:
        return context, False

    # Trim from longest entries first.
    excess = total - max_chars
    sorted_flat = sorted(flat, key=lambda x: len(x[1]), reverse=True)
    trimmed: dict[str | tuple[str, int], str] = {path: val for path, val in sorted_flat}

    for path, val in sorted_flat:
        if excess <= 0:
            break
        trim_amount = min(excess, len(val) - 1)
        if trim_amount > 0:
            trimmed[path] = val[: len(val) - trim_amount]
            excess -= trim_amount

    # Rebuild context
    result: dict[str, Any] = {}
    for key, val in context.items():
        if isinstance(val, str):
            result[key] = trimmed.get(key, val)
        elif isinstance(val, list):
            new_list: list[Any] = []
            for idx, item in enumerate(val):
                if isinstance(item, str):
                    new_list.append(trimmed.get((key, idx), item))
                else:
                    new_list.append(item)
            result[key] = new_list
        else:
            result[key] = val

    return result, True


def _build_user_context(source: dict[str, Any], max_context_chars: int) -> tuple[dict[str, Any], int, bool]:
    """Build sanitized, bounded user_context from a research artifact.

    Returns (context, redacted_count, was_truncated).
    """
    raw_context: dict[str, Any] = {
        "symbol": source.get("symbol", ""),
        "summary": source.get("summary", ""),
        "thesis": source.get("thesis", ""),
        "market_context": source.get("market_context", ""),
        "risks": list(source.get("risks", [])),
        "invalidation_conditions": list(source.get("invalidation_conditions", [])),
        "paper_only_plan": source.get("paper_only_plan", ""),
    }
    citations = source.get("citations", [])
    if citations:
        raw_context["citations"] = list(citations)

    # Sanitize first
    sanitized_context, redacted_count = _sanitize_prompt_value(raw_context)

    # Then truncate
    truncated_context, was_truncated = _truncate_user_context(sanitized_context, max_context_chars)

    return truncated_context, redacted_count, was_truncated


def generate_prompt_packet(
    workspace_path: Path,
    run_id: str,
    *,
    max_context_chars: int = 8000,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Generate a sanitized, bounded prompt packet from an existing research artifact.

    This never calls LLMs, networks, brokers, or reads API keys.
    """
    if not isinstance(max_context_chars, int):
        raise ResearchSessionError("invalid_max_context_chars")
    if max_context_chars <= 0:
        raise ResearchSessionError("invalid_max_context_chars")
    if max_context_chars > 20000:
        raise ResearchSessionError("max_context_chars_exceeds_limit")

    safe_run_id = validate_run_id(run_id)

    source_path = find_research_artifact_by_run_id(workspace_path, safe_run_id)
    if source_path is None:
        raise ResearchSessionError("artifact_not_found")
    source = load_research_artifact(source_path, workspace_path)

    raw_symbol = source.get("symbol", "")
    if not raw_symbol:
        raise ResearchSessionError("invalid_research_symbol")
    try:
        symbol = sanitize_symbol(raw_symbol)
    except InvalidResearchSymbolError:
        raise ResearchSessionError("invalid_research_symbol")

    prompt_packet_id = generate_run_id()
    created_at = datetime.now(UTC)

    user_context, redacted_count, was_truncated = _build_user_context(source, max_context_chars)

    system_boundary = {
        "paper_only": True,
        "analysis_only": True,
        "no_trading_advice": True,
        "no_live_trading_authorization": True,
        "no_broker_submit": True,
        "no_pending_orders": True,
        "no_approvals": True,
        "no_api_network_call_required": True,
    }

    allowed_uses = [
        "Local analysis and review.",
        "Input to future research providers (when enabled).",
        "Paper workflow preparation.",
    ]

    forbidden_uses = [
        "Live trading authorization.",
        "Direct order generation.",
        "Financial advice to third parties.",
        "Bypassing risk gates or approval workflows.",
    ]

    warnings = [
        "This is a deterministic local artifact. No LLM was consulted.",
        "Verify all assumptions before any trading decision.",
    ]

    source_artifact_path = source.get("artifact_path", "")
    if not source_artifact_path:
        source_artifact_path = source_path.relative_to(workspace_path).as_posix()

    # Ensure prompts directory exists
    prompts_dir = workspace_path / RESEARCH_DIR / symbol / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    artifact_path_rel = f".atlas/research/{symbol}/prompts/{prompt_packet_id}.json"
    artifact_path = workspace_path / artifact_path_rel

    redaction_summary = {
        "redacted_fragments_count": redacted_count,
        "truncated": was_truncated,
    }

    packet: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "prompt_packet_id": prompt_packet_id,
        "source_run_id": safe_run_id,
        "created_at": created_at.isoformat(),
        "symbol": symbol,
        "mode": "paper",
        "provider": "deterministic",
        "source_artifact_path": source_artifact_path,
        "max_context_chars": max_context_chars,
        "system_boundary": system_boundary,
        "user_context": user_context,
        "allowed_uses": allowed_uses,
        "forbidden_uses": forbidden_uses,
        "redaction_summary": redaction_summary,
        "warnings": warnings,
        "metadata": {
            "max_context_chars": max_context_chars,
            "source_schema_version": source.get("schema_version", ""),
        },
        "artifact_path": artifact_path_rel,
    }

    artifact_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")

    # Log safe event
    if event_logger is not None:
        payload = {
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": safe_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": "deterministic",
            "artifact_path": artifact_path_rel,
            "status": "created",
            "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        }
        event_logger.write(
            "research_prompt_packet_created",
            run_id=prompt_packet_id,
            command="atlas research prompt",
            mode="paper",
            payload=payload,
        )

    return packet


# ---------------------------------------------------------------------------
# Simulated provider response generation
# ---------------------------------------------------------------------------

SUPPORTED_SIMULATION_PROVIDERS = {"deterministic-mock"}

_PROVIDER_RESPONSE_DANGEROUS_PHRASES = (
    "submit live order",
    "live submit authorized",
    "create pending order",
    "create approval",
    "place order",
    "execute trade",
    "buy recommendation",
    "sell recommendation",
    "trading signal",
    "expected profit",
    "guaranteed profit",
    "guaranteed return",
    "risk-free",
    "zero risk",
    "no risk",
    "production-ready live trading",
    "safe live trading",
    "autonomous live trading",
    "financial advice",
)


@dataclass(frozen=True)
class ProviderResponseArtifact:
    provider_response_id: str
    source_prompt_packet_id: str
    source_run_id: str
    created_at: datetime
    symbol: str
    mode: str
    provider: str
    provider_status: str
    source_prompt_packet_path: str
    response_summary: str
    response_sections: dict[str, Any]
    safety_checks: list[dict[str, str]]
    passed_checks: int
    failed_checks: int
    recommendation: str
    redaction_summary: dict[str, Any]
    warnings: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION
    artifact_path: str = ""


@dataclass(frozen=True)
class ResponseReviewArtifact:
    response_review_id: str
    source_provider_response_id: str
    source_prompt_packet_id: str
    source_run_id: str
    created_at: datetime
    symbol: str
    mode: str
    provider: str
    source_provider_response_path: str
    review_status: str
    checks: list[dict[str, str]]
    passed_checks: int
    failed_checks: int
    recommendation: str
    redaction_summary: dict[str, Any]
    warnings: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION
    artifact_path: str = ""


def find_prompt_packet_by_id(workspace_path: Path, prompt_packet_id: str) -> Path | None:
    """Find exactly one prompt packet artifact by prompt_packet_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_id = validate_run_id(prompt_packet_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        prompts_dir = sym_dir / "prompts"
        if not prompts_dir.exists():
            continue
        candidate = prompts_dir / f"{safe_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_prompt_packet_id")
    return matches[0]


def load_prompt_packet(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a prompt packet JSON safely."""
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("prompt_packet_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("prompt_packet_malformed")
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_prompt_packet_schema")
    return data


def find_provider_response_by_id(workspace_path: Path, provider_response_id: str) -> Path | None:
    """Find exactly one provider response artifact by provider_response_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_id = validate_run_id(provider_response_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        responses_dir = sym_dir / "provider_responses"
        if not responses_dir.exists():
            continue
        candidate = responses_dir / f"{safe_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_response_id")
    return matches[0]


def load_provider_response(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a provider response JSON safely."""
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("provider_response_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_response_malformed")
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_provider_response_schema")
    return data


def _check_prompt_packet_loaded(prompt: dict[str, Any]) -> dict[str, str]:
    if prompt.get("prompt_packet_id"):
        return {"name": "prompt_packet_loaded", "status": "pass", "message": "Prompt packet loaded."}
    return {"name": "prompt_packet_loaded", "status": "fail", "message": "Prompt packet not loaded."}


def _check_prompt_schema_supported(prompt: dict[str, Any]) -> dict[str, str]:
    sv = prompt.get("schema_version")
    if sv is None or sv == RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return {"name": "prompt_schema_supported", "status": "pass", "message": "Prompt schema is supported."}
    return {"name": "prompt_schema_supported", "status": "fail", "message": "Prompt schema is unsupported."}


def _check_paper_only_mode_response(prompt: dict[str, Any]) -> dict[str, str]:
    if prompt.get("mode") == "paper":
        return {"name": "paper_only_mode", "status": "pass", "message": "Mode is paper."}
    return {"name": "paper_only_mode", "status": "fail", "message": "Mode is not paper."}


def _check_provider_is_simulated(provider: str) -> dict[str, str]:
    if provider in SUPPORTED_SIMULATION_PROVIDERS:
        return {"name": "provider_is_simulated", "status": "pass", "message": "Provider is simulated."}
    return {"name": "provider_is_simulated", "status": "fail", "message": "Provider is not simulated."}


def _check_no_network_provider(provider: str) -> dict[str, str]:
    if provider in SUPPORTED_SIMULATION_PROVIDERS:
        return {"name": "no_network_provider", "status": "pass", "message": "No network provider used."}
    return {"name": "no_network_provider", "status": "fail", "message": "Network provider detected."}


def _check_no_api_key_required(provider: str) -> dict[str, str]:
    if provider in SUPPORTED_SIMULATION_PROVIDERS:
        return {"name": "no_api_key_required", "status": "pass", "message": "No API key required."}
    return {"name": "no_api_key_required", "status": "fail", "message": "API key may be required."}


def _check_no_live_authorization_language_response(text: str) -> dict[str, str]:
    lower = text.lower()
    for phrase in _PROVIDER_RESPONSE_DANGEROUS_PHRASES:
        idx = lower.find(phrase.lower())
        if idx == -1:
            continue
        window_start = max(0, idx - 40)
        context = lower[window_start:idx]
        negative_indicators = ("not ", "does not ", "never ", "no ", "without ")
        if any(context.endswith(ind) or (" " + ind) in context for ind in negative_indicators):
            continue
        return {"name": "no_live_authorization_language", "status": "fail", "message": "Response contains disallowed language."}
    return {"name": "no_live_authorization_language", "status": "pass", "message": "No disallowed language found."}


def _check_no_order_language(text: str) -> dict[str, str]:
    lower = text.lower()
    order_phrases = ("place order", "execute trade", "create pending order", "submit live order")
    for phrase in order_phrases:
        if phrase.lower() in lower:
            return {"name": "no_order_language", "status": "fail", "message": "Response contains order language."}
    return {"name": "no_order_language", "status": "pass", "message": "No order language found."}


def _check_no_financial_advice_language(text: str) -> dict[str, str]:
    lower = text.lower()
    advice_phrases = ("financial advice", "buy recommendation", "sell recommendation", "trading signal", "expected profit", "guaranteed profit", "guaranteed return")
    for phrase in advice_phrases:
        if phrase.lower() in lower:
            return {"name": "no_financial_advice_language", "status": "fail", "message": "Response contains financial advice language."}
    return {"name": "no_financial_advice_language", "status": "pass", "message": "No financial advice language found."}


def _check_no_secret_fragments(text: str) -> dict[str, str]:
    forbidden = ("Authorization", "Bearer", "APCA", "SECRET", "TOKEN", "PASSWORD", "API_KEY", "sk-", "/Users/", "/private/var/", "broker.example.com")
    for frag in forbidden:
        if frag in text:
            return {"name": "no_secret_fragments", "status": "fail", "message": "Response contains forbidden fragments."}
    return {"name": "no_secret_fragments", "status": "pass", "message": "No secret fragments found."}


def _check_response_bounded(response_sections: dict[str, Any]) -> dict[str, str]:
    total = len(json.dumps(response_sections))
    if total <= 50000:
        return {"name": "response_bounded", "status": "pass", "message": "Response is bounded."}
    return {"name": "response_bounded", "status": "fail", "message": "Response exceeds size limit."}


def _check_source_path_contained_response(prompt: dict[str, Any], workspace_path: Path) -> dict[str, str]:
    source_path = prompt.get("source_artifact_path", "") or prompt.get("artifact_path", "")
    if not source_path:
        return {"name": "source_path_contained", "status": "fail", "message": "Source path is missing."}
    if source_path.startswith("/"):
        try:
            p = Path(source_path).resolve()
            ws = workspace_path.resolve()
            p.relative_to(ws)
        except ValueError:
            return {"name": "source_path_contained", "status": "fail", "message": "Source path is outside workspace."}
    return {"name": "source_path_contained", "status": "pass", "message": "Source path is contained."}


# ---------------------------------------------------------------------------
# Response review checks
# ---------------------------------------------------------------------------

def _check_provider_response_loaded(response: dict[str, Any]) -> dict[str, str]:
    if response.get("provider_response_id"):
        return {"name": "provider_response_loaded", "status": "pass", "message": "Provider response loaded."}
    return {"name": "provider_response_loaded", "status": "fail", "message": "Provider response not loaded."}


def _check_provider_response_schema_supported(response: dict[str, Any]) -> dict[str, str]:
    sv = response.get("schema_version")
    if sv is None or sv == RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return {"name": "provider_response_schema_supported", "status": "pass", "message": "Provider response schema is supported."}
    return {"name": "provider_response_schema_supported", "status": "fail", "message": "Provider response schema is unsupported."}


def _check_provider_status_is_simulated(response: dict[str, Any]) -> dict[str, str]:
    if response.get("provider_status") == "simulated":
        return {"name": "provider_status_is_simulated", "status": "pass", "message": "Provider status is simulated."}
    return {"name": "provider_status_is_simulated", "status": "fail", "message": "Provider status is not simulated."}


def _check_source_prompt_packet_id_present(response: dict[str, Any]) -> dict[str, str]:
    if response.get("source_prompt_packet_id"):
        return {"name": "source_prompt_packet_id_present", "status": "pass", "message": "Source prompt packet ID is present."}
    return {"name": "source_prompt_packet_id_present", "status": "fail", "message": "Source prompt packet ID is missing."}


def _check_source_run_id_valid(response: dict[str, Any]) -> dict[str, str]:
    raw = response.get("source_run_id", "")
    if not raw:
        return {"name": "source_run_id_valid", "status": "fail", "message": "Source run ID is missing."}
    try:
        validate_run_id(raw)
        return {"name": "source_run_id_valid", "status": "pass", "message": "Source run ID is valid."}
    except ResearchSessionError:
        return {"name": "source_run_id_valid", "status": "fail", "message": "Source run ID is invalid."}


def _check_symbol_valid_response(response: dict[str, Any]) -> dict[str, str]:
    raw = response.get("symbol", "")
    if not raw:
        return {"name": "symbol_valid", "status": "fail", "message": "Symbol is missing."}
    try:
        sanitize_symbol(raw)
        return {"name": "symbol_valid", "status": "pass", "message": "Symbol is valid."}
    except InvalidResearchSymbolError:
        return {"name": "symbol_valid", "status": "fail", "message": "Symbol is invalid."}


def _check_response_sections_present(response: dict[str, Any]) -> dict[str, str]:
    if response.get("response_sections"):
        return {"name": "response_sections_present", "status": "pass", "message": "Response sections are present."}
    return {"name": "response_sections_present", "status": "fail", "message": "Response sections are missing."}


def _check_response_summary_present(response: dict[str, Any]) -> dict[str, str]:
    if response.get("response_summary"):
        return {"name": "response_summary_present", "status": "pass", "message": "Response summary is present."}
    return {"name": "response_summary_present", "status": "fail", "message": "Response summary is missing."}


def _check_safety_checks_present(response: dict[str, Any]) -> dict[str, str]:
    if isinstance(response.get("safety_checks"), list):
        return {"name": "safety_checks_present", "status": "pass", "message": "Safety checks are present."}
    return {"name": "safety_checks_present", "status": "fail", "message": "Safety checks are missing."}


def _check_no_trading_signal_language(text: str) -> dict[str, str]:
    lower = text.lower()
    signal_phrases = ("trading signal", "buy recommendation", "sell recommendation", "signal generated")
    for phrase in signal_phrases:
        if phrase.lower() in lower:
            return {"name": "no_trading_signal_language", "status": "fail", "message": "Response contains trading signal language."}
    return {"name": "no_trading_signal_language", "status": "pass", "message": "No trading signal language found."}


def _check_no_profitability_claims(text: str) -> dict[str, str]:
    lower = text.lower()
    profit_phrases = ("expected profit", "guaranteed profit", "guaranteed return", "risk-free", "zero risk", "no risk")
    for phrase in profit_phrases:
        if phrase.lower() in lower:
            return {"name": "no_profitability_claims", "status": "fail", "message": "Response contains profitability claims."}
    return {"name": "no_profitability_claims", "status": "pass", "message": "No profitability claims found."}


def _check_response_bounded_review(response: dict[str, Any]) -> dict[str, str]:
    sections = response.get("response_sections", {})
    total = len(json.dumps(sections))
    if total <= 50000:
        return {"name": "response_bounded", "status": "pass", "message": "Response is bounded."}
    return {"name": "response_bounded", "status": "fail", "message": "Response exceeds size limit."}


def _check_source_path_contained_review(response: dict[str, Any], workspace_path: Path) -> dict[str, str]:
    source_path = response.get("source_prompt_packet_path", "") or response.get("artifact_path", "")
    if not source_path:
        return {"name": "source_path_contained", "status": "fail", "message": "Source path is missing."}
    if source_path.startswith("/"):
        try:
            p = Path(source_path).resolve()
            ws = workspace_path.resolve()
            p.relative_to(ws)
        except ValueError:
            return {"name": "source_path_contained", "status": "fail", "message": "Source path is outside workspace."}
    return {"name": "source_path_contained", "status": "pass", "message": "Source path is contained."}


def _redact_dangerous_phrases(text: str) -> str:
    """Redact dangerous phrases from text. Returns sanitized text."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for phrase in _PROVIDER_RESPONSE_DANGEROUS_PHRASES:
        sanitized = re.sub(re.escape(phrase), "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


def _redact_dangerous_in_value(value: Any) -> Any:
    """Recursively redact dangerous phrases from a value."""
    if isinstance(value, str):
        return _redact_dangerous_phrases(value)
    if isinstance(value, list):
        return [_redact_dangerous_in_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _redact_dangerous_in_value(v) for k, v in value.items()}
    return value


def _generate_deterministic_mock_response(prompt: dict[str, Any]) -> dict[str, Any]:
    """Generate a bounded, local, safe deterministic mock response."""
    symbol = prompt.get("symbol", "UNKNOWN")
    user_context = prompt.get("user_context", {})

    summary = user_context.get("summary", "No summary available.")
    thesis = user_context.get("thesis", "No thesis available.")
    risks = user_context.get("risks", [])
    invalidation = user_context.get("invalidation_conditions", [])

    # Sanitize user-derived fields before interpolation to prevent forbidden fragments
    # from leaking into response sections.
    safe_summary, _ = _sanitize_prompt_text(str(summary))
    safe_thesis, _ = _sanitize_prompt_text(str(thesis))
    safe_risks = [_sanitize_prompt_text(str(r))[0] for r in risks]
    safe_invalidation = [_sanitize_prompt_text(str(i))[0] for i in invalidation]

    response_sections: dict[str, Any] = {
        "scope_review": f"Scope: review local analysis artifact for {symbol}. This is a paper-only simulation.",
        "context_summary": f"Context summary for {symbol}: {safe_summary[:500]}",
        "risk_review": f"Identified risks: {len(safe_risks)}. Review each risk before any trading decision.",
        "invalidation_review": f"Invalidation conditions: {len(safe_invalidation)}. Monitor for changes that invalidate assumptions.",
        "paper_only_review": "This response is generated by a deterministic mock provider. It is paper-only and does not authorize live trading, create orders, or provide financial advice.",
        "follow_up_questions": [
            "What additional local data would strengthen this analysis?",
            "What risk limits should be reviewed before any separate approval workflow?",
        ],
    }

    if safe_risks:
        response_sections["risk_review_details"] = [r[:300] for r in safe_risks[:10]]
    if safe_invalidation:
        response_sections["invalidation_review_details"] = [i[:300] for i in safe_invalidation[:10]]

    return response_sections


def simulate_provider_response(
    workspace_path: Path,
    prompt_packet_id: str,
    provider: str = "deterministic-mock",
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Generate a local simulated provider response artifact from a prompt packet.

    This never calls LLMs, networks, brokers, or reads API keys.
    """
    safe_prompt_id = validate_run_id(prompt_packet_id)

    if provider not in SUPPORTED_SIMULATION_PROVIDERS:
        raise UnsupportedResearchProviderError("unsupported_research_provider")

    # Find and load prompt packet
    prompt_path = find_prompt_packet_by_id(workspace_path, safe_prompt_id)
    if prompt_path is None:
        raise ResearchSessionError("prompt_packet_not_found")
    prompt = load_prompt_packet(prompt_path, workspace_path)

    # Validate symbol
    raw_symbol = prompt.get("symbol", "")
    if not raw_symbol:
        raise ResearchSessionError("invalid_research_symbol")
    try:
        symbol = sanitize_symbol(raw_symbol)
    except InvalidResearchSymbolError:
        raise ResearchSessionError("invalid_research_symbol")

    provider_response_id = generate_run_id()
    created_at = datetime.now(UTC)

    # Validate source_run_id from prompt packet — fail closed if missing/invalid/unsafe
    raw_source_run_id = prompt.get("source_run_id", "")
    if not raw_source_run_id:
        raise ResearchSessionError("invalid_research_identifier")
    try:
        source_run_id = validate_run_id(raw_source_run_id)
    except ResearchSessionError:
        raise ResearchSessionError("invalid_research_identifier")
    # Additional safety: reject forbidden fragments in source_run_id
    _sanitized_run_id, _run_id_redacted = _sanitize_prompt_text(source_run_id)
    if _run_id_redacted > 0:
        raise ResearchSessionError("invalid_research_identifier")

    # Sanitize source prompt packet path from prompt packet — never trust raw paths
    raw_source_prompt_packet_path = prompt.get("artifact_path", "")
    if raw_source_prompt_packet_path:
        source_prompt_packet_path, _ = _sanitize_prompt_text(str(raw_source_prompt_packet_path))
    else:
        source_prompt_packet_path = prompt_path.relative_to(workspace_path).as_posix()

    # Generate deterministic mock response (raw)
    raw_response_sections = _generate_deterministic_mock_response(prompt)

    # Build full text for safety checks on raw response
    raw_full_text = json.dumps(raw_response_sections, sort_keys=True)

    # Run safety checks on raw response before redaction
    checks: list[dict[str, str]] = [
        _check_prompt_packet_loaded(prompt),
        _check_prompt_schema_supported(prompt),
        _check_paper_only_mode_response(prompt),
        _check_provider_is_simulated(provider),
        _check_no_network_provider(provider),
        _check_no_api_key_required(provider),
        _check_no_live_authorization_language_response(raw_full_text),
        _check_no_order_language(raw_full_text),
        _check_no_financial_advice_language(raw_full_text),
        _check_no_secret_fragments(raw_full_text),
        _check_response_bounded(raw_response_sections),
        _check_source_path_contained_response(prompt, workspace_path),
    ]

    passed_checks = sum(1 for c in checks if c["status"] == "pass")
    failed_checks = sum(1 for c in checks if c["status"] == "fail")

    if failed_checks == 0:
        recommendation = "provider_response_review_ready"
    else:
        recommendation = "manual_review_required"

    # Redact dangerous phrases from response if any safety checks failed
    if failed_checks > 0:
        response_sections = _redact_dangerous_in_value(raw_response_sections)
    else:
        response_sections = raw_response_sections

    # Sanitize response sections for secrets/paths
    sanitized_sections, redacted_count = _sanitize_prompt_value(response_sections)

    # Also sanitize safety check messages to avoid leaking forbidden fragments in artifact
    sanitized_checks, _ = _sanitize_prompt_value(checks)

    warnings: list[str] = []
    if redacted_count > 0:
        warnings.append("response_content_redacted")
    if failed_checks > 0:
        warnings.append("safety_checks_failed")

    response_summary = f"Deterministic mock provider response for {symbol}. Paper-only. No trading signals."
    safe_response_summary, _ = _sanitize_prompt_text(response_summary)

    redaction_summary = {
        "redacted_fragments_count": redacted_count,
    }

    artifact_path_rel = f".atlas/research/{symbol}/provider_responses/{provider_response_id}.json"

    # Sanitize source provider metadata to known safe values only
    _KNOWN_SAFE_PROVIDERS = {"deterministic", "deterministic-mock", "unknown"}
    raw_source_provider = prompt.get("provider", "unknown")
    source_provider = raw_source_provider if raw_source_provider in _KNOWN_SAFE_PROVIDERS else "unknown"

    artifact = ProviderResponseArtifact(
        provider_response_id=provider_response_id,
        source_prompt_packet_id=safe_prompt_id,
        source_run_id=source_run_id,
        created_at=created_at,
        symbol=symbol,
        mode="paper",
        provider=provider,
        provider_status="simulated",
        source_prompt_packet_path=source_prompt_packet_path,
        response_summary=safe_response_summary,
        response_sections=sanitized_sections,
        safety_checks=sanitized_checks,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        recommendation=recommendation,
        redaction_summary=redaction_summary,
        warnings=warnings,
        artifact_path=artifact_path_rel,
        metadata={
            "provider_requested": provider,
            "source_provider": source_provider,
        },
    )

    # Persist
    responses_dir = workspace_path / RESEARCH_DIR / symbol / "provider_responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    response_file = responses_dir / f"{provider_response_id}.json"
    _write_provider_response_safe_json(response_file, artifact)

    # Rebuild with final artifact_path
    artifact = ProviderResponseArtifact(
        provider_response_id=artifact.provider_response_id,
        source_prompt_packet_id=artifact.source_prompt_packet_id,
        source_run_id=artifact.source_run_id,
        created_at=artifact.created_at,
        symbol=artifact.symbol,
        mode=artifact.mode,
        provider=artifact.provider,
        provider_status=artifact.provider_status,
        source_prompt_packet_path=artifact.source_prompt_packet_path,
        response_summary=artifact.response_summary,
        response_sections=artifact.response_sections,
        safety_checks=artifact.safety_checks,
        passed_checks=artifact.passed_checks,
        failed_checks=artifact.failed_checks,
        recommendation=artifact.recommendation,
        redaction_summary=artifact.redaction_summary,
        warnings=artifact.warnings,
        artifact_path=response_file.relative_to(workspace_path).as_posix(),
        metadata=artifact.metadata,
    )

    result: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "provider_response_id": artifact.provider_response_id,
        "source_prompt_packet_id": artifact.source_prompt_packet_id,
        "source_run_id": artifact.source_run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "provider_status": artifact.provider_status,
        "source_prompt_packet_path": artifact.source_prompt_packet_path,
        "response_summary": artifact.response_summary,
        "response_sections": artifact.response_sections,
        "safety_checks": artifact.safety_checks,
        "passed_checks": artifact.passed_checks,
        "failed_checks": artifact.failed_checks,
        "recommendation": artifact.recommendation,
        "redaction_summary": artifact.redaction_summary,
        "warnings": artifact.warnings,
        "metadata": artifact.metadata,
        "artifact_path": artifact.artifact_path,
    }

    # Log safe event — sanitize payload strings as defense-in-depth
    if event_logger is not None:
        payload = {
            "provider_response_id": provider_response_id,
            "source_prompt_packet_id": safe_prompt_id,
            "source_run_id": source_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": provider,
            "provider_status": "simulated",
            "recommendation": recommendation,
            "artifact_path": artifact.artifact_path,
            "status": "created",
            "schema_version": artifact.schema_version,
        }
        safe_payload, _ = _sanitize_prompt_value(payload)
        event_logger.write(
            "research_provider_response_created",
            run_id=provider_response_id,
            command="atlas research simulate-provider",
            mode="paper",
            payload=safe_payload,
        )

    return result


def review_provider_response(
    workspace_path: Path,
    provider_response_id: str,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Generate a local deterministic review of a provider response artifact.

    This never calls LLMs, networks, brokers, or reads API keys.
    """
    safe_response_id = validate_run_id(provider_response_id)

    # Find and load provider response artifact
    response_path = find_provider_response_by_id(workspace_path, safe_response_id)
    if response_path is None:
        raise ResearchSessionError("provider_response_not_found")
    response = load_provider_response(response_path, workspace_path)

    # Validate symbol
    raw_symbol = response.get("symbol", "")
    if not raw_symbol:
        raise ResearchSessionError("invalid_research_symbol")
    try:
        symbol = sanitize_symbol(raw_symbol)
    except InvalidResearchSymbolError:
        raise ResearchSessionError("invalid_research_symbol")

    response_review_id = generate_run_id()
    created_at = datetime.now(UTC)
    source_prompt_packet_id = response.get("source_prompt_packet_id", "")
    source_run_id = response.get("source_run_id", "")

    # Validate lineage IDs — fail closed on tampered/missing/unsafe values
    if not source_prompt_packet_id:
        raise ResearchSessionError("invalid_research_identifier")
    try:
        validate_run_id(source_prompt_packet_id)
    except ResearchSessionError:
        raise ResearchSessionError("invalid_research_identifier")
    _sanitized_ppid, _ppid_redacted = _sanitize_prompt_text(source_prompt_packet_id)
    if _ppid_redacted > 0:
        raise ResearchSessionError("invalid_research_identifier")

    if not source_run_id:
        raise ResearchSessionError("invalid_research_identifier")
    try:
        validate_run_id(source_run_id)
    except ResearchSessionError:
        raise ResearchSessionError("invalid_research_identifier")
    _sanitized_rid, _rid_redacted = _sanitize_prompt_text(source_run_id)
    if _rid_redacted > 0:
        raise ResearchSessionError("invalid_research_identifier")

    source_provider_response_path = response.get("artifact_path", "")
    if not source_provider_response_path:
        source_provider_response_path = response_path.relative_to(workspace_path).as_posix()

    # Build review text for safety checks
    response_text = json.dumps(response.get("response_sections", {}), sort_keys=True)
    response_summary = str(response.get("response_summary", ""))
    full_text = response_text + " " + response_summary

    # Run review checks
    checks: list[dict[str, str]] = [
        _check_provider_response_loaded(response),
        _check_provider_response_schema_supported(response),
        _check_paper_only_mode_response(response),
        _check_provider_status_is_simulated(response),
        _check_source_prompt_packet_id_present(response),
        _check_source_run_id_valid(response),
        _check_symbol_valid_response(response),
        _check_response_sections_present(response),
        _check_response_summary_present(response),
        _check_safety_checks_present(response),
        _check_no_live_authorization_language_response(full_text),
        _check_no_order_language(full_text),
        _check_no_financial_advice_language(full_text),
        _check_no_trading_signal_language(full_text),
        _check_no_profitability_claims(full_text),
        _check_no_secret_fragments(full_text),
        _check_source_path_contained_review(response, workspace_path),
        _check_response_bounded_review(response),
    ]

    passed_checks = sum(1 for c in checks if c["status"] == "pass")
    failed_checks = sum(1 for c in checks if c["status"] == "fail")

    if failed_checks == 0:
        recommendation = "provider_response_review_ready"
        review_status = "review_passed"
    else:
        recommendation = "manual_review_required"
        review_status = "review_failed"

    # Sanitize check messages to avoid leaking forbidden fragments
    sanitized_checks, _ = _sanitize_prompt_value(checks)

    warnings: list[str] = []
    if failed_checks > 0:
        warnings.append("review_checks_failed")

    redaction_summary = {
        "redacted_fragments_count": 0,
    }

    artifact_path_rel = f".atlas/research/{symbol}/response_reviews/{response_review_id}.json"

    artifact = ResponseReviewArtifact(
        response_review_id=response_review_id,
        source_provider_response_id=safe_response_id,
        source_prompt_packet_id=source_prompt_packet_id,
        source_run_id=source_run_id,
        created_at=created_at,
        symbol=symbol,
        mode="paper",
        provider="deterministic-review",
        source_provider_response_path=source_provider_response_path,
        review_status=review_status,
        checks=sanitized_checks,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        recommendation=recommendation,
        redaction_summary=redaction_summary,
        warnings=warnings,
        artifact_path=artifact_path_rel,
        metadata={
            "review_provider": "deterministic-review",
        },
    )

    # Persist
    reviews_dir = workspace_path / RESEARCH_DIR / symbol / "response_reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    review_file = reviews_dir / f"{response_review_id}.json"
    _write_response_review_safe_json(review_file, artifact)

    # Rebuild with final artifact_path
    artifact = ResponseReviewArtifact(
        response_review_id=artifact.response_review_id,
        source_provider_response_id=artifact.source_provider_response_id,
        source_prompt_packet_id=artifact.source_prompt_packet_id,
        source_run_id=artifact.source_run_id,
        created_at=artifact.created_at,
        symbol=artifact.symbol,
        mode=artifact.mode,
        provider=artifact.provider,
        source_provider_response_path=artifact.source_provider_response_path,
        review_status=artifact.review_status,
        checks=artifact.checks,
        passed_checks=artifact.passed_checks,
        failed_checks=artifact.failed_checks,
        recommendation=artifact.recommendation,
        redaction_summary=artifact.redaction_summary,
        warnings=artifact.warnings,
        artifact_path=review_file.relative_to(workspace_path).as_posix(),
        metadata=artifact.metadata,
    )

    result: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "response_review_id": artifact.response_review_id,
        "source_provider_response_id": artifact.source_provider_response_id,
        "source_prompt_packet_id": artifact.source_prompt_packet_id,
        "source_run_id": artifact.source_run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "review_status": artifact.review_status,
        "source_provider_response_path": artifact.source_provider_response_path,
        "checks": artifact.checks,
        "passed_checks": artifact.passed_checks,
        "failed_checks": artifact.failed_checks,
        "recommendation": artifact.recommendation,
        "redaction_summary": artifact.redaction_summary,
        "warnings": artifact.warnings,
        "metadata": artifact.metadata,
        "artifact_path": artifact.artifact_path,
    }
    result, _ = _sanitize_prompt_value(result)

    # Log safe event
    if event_logger is not None:
        payload = {
            "response_review_id": response_review_id,
            "source_provider_response_id": safe_response_id,
            "source_prompt_packet_id": source_prompt_packet_id,
            "source_run_id": source_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": "deterministic-review",
            "recommendation": recommendation,
            "artifact_path": artifact.artifact_path,
            "status": "created",
            "schema_version": artifact.schema_version,
        }
        safe_payload, _ = _sanitize_prompt_value(payload)
        event_logger.write(
            "research_response_review_created",
            run_id=response_review_id,
            command="atlas research review-response",
            mode="paper",
            payload=safe_payload,
        )

    return result


def _write_provider_response_safe_json(path: Path, artifact: ProviderResponseArtifact) -> None:
    data: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "provider_response_id": artifact.provider_response_id,
        "source_prompt_packet_id": artifact.source_prompt_packet_id,
        "source_run_id": artifact.source_run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "provider_status": artifact.provider_status,
        "source_prompt_packet_path": artifact.source_prompt_packet_path,
        "response_summary": artifact.response_summary,
        "response_sections": artifact.response_sections,
        "safety_checks": artifact.safety_checks,
        "passed_checks": artifact.passed_checks,
        "failed_checks": artifact.failed_checks,
        "recommendation": artifact.recommendation,
        "redaction_summary": artifact.redaction_summary,
        "warnings": artifact.warnings,
        "metadata": artifact.metadata,
        "artifact_path": artifact.artifact_path,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_response_review_safe_json(path: Path, artifact: ResponseReviewArtifact) -> None:
    data: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "response_review_id": artifact.response_review_id,
        "source_provider_response_id": artifact.source_provider_response_id,
        "source_prompt_packet_id": artifact.source_prompt_packet_id,
        "source_run_id": artifact.source_run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "source_provider_response_path": artifact.source_provider_response_path,
        "review_status": artifact.review_status,
        "checks": artifact.checks,
        "passed_checks": artifact.passed_checks,
        "failed_checks": artifact.failed_checks,
        "recommendation": artifact.recommendation,
        "redaction_summary": artifact.redaction_summary,
        "warnings": artifact.warnings,
        "metadata": artifact.metadata,
        "artifact_path": artifact.artifact_path,
    }
    safe_data, _ = _sanitize_prompt_value(data)
    path.write_text(json.dumps(safe_data, indent=2, sort_keys=True), encoding="utf-8")



@dataclass(frozen=True)
class DossierArtifact:
    dossier_id: str
    source_run_id: str
    created_at: datetime
    symbol: str
    mode: str
    provider: str
    source_research_path: str
    workflow_status: dict[str, bool]
    artifact_counts: dict[str, int]
    linked_artifacts: list[dict[str, Any]]
    summaries: dict[str, Any]
    safety_summary: dict[str, Any]
    missing_links: list[str]
    warnings: list[str]
    recommendation: str
    redaction_summary: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION
    artifact_path: str = ""


def build_dossier(
    workspace_path: Path,
    run_id: str,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Build a local deterministic dossier that consolidates a research chain.

    This never calls LLMs, networks, brokers, or reads API keys.
    """
    safe_run_id = validate_run_id(run_id)

    # Load research artifact
    research_path = find_research_artifact_by_run_id(workspace_path, safe_run_id)
    if research_path is None:
        raise ResearchSessionError("artifact_not_found")
    research = load_research_artifact(research_path, workspace_path)

    # Validate symbol
    raw_symbol = research.get("symbol", "")
    if not raw_symbol:
        raise ResearchSessionError("invalid_research_symbol")
    try:
        symbol = sanitize_symbol(raw_symbol)
    except InvalidResearchSymbolError:
        raise ResearchSessionError("invalid_research_symbol")

    dossier_id = generate_run_id()
    created_at = datetime.now(UTC)
    source_research_path = research.get("artifact_path", "")
    if not source_research_path:
        source_research_path = research_path.relative_to(workspace_path).as_posix()

    # Find linked artifacts using existing safe iterators
    plan_items = iter_plan_artifacts(workspace_path, symbol=symbol)
    verification_items = _iter_verification_artifacts(workspace_path, symbol=symbol)
    evaluation_items = _iter_evaluation_artifacts(workspace_path, symbol=symbol)
    prompt_items = _iter_prompt_artifacts(workspace_path, symbol=symbol)
    provider_response_items = _iter_provider_response_artifacts(workspace_path, symbol=symbol)
    response_review_items = _iter_response_review_artifacts(workspace_path, symbol=symbol)
    sandbox_request_items = _iter_sandbox_request_artifacts(workspace_path, symbol=symbol)

    # Filter plans linked to this run
    linked_plans = [p for p in plan_items if p.get("source_run_id") == safe_run_id]
    linked_plan_ids = {p.get("plan_id", "") for p in linked_plans}

    linked_verifications = [v for v in verification_items if v.get("source_plan_id") in linked_plan_ids]
    linked_evaluations = [e for e in evaluation_items if e.get("source_plan_id") in linked_plan_ids]

    linked_prompts = [p for p in prompt_items if p.get("source_run_id") == safe_run_id]
    linked_prompt_ids = {p.get("prompt_packet_id", "") for p in linked_prompts}

    linked_provider_responses = [pr for pr in provider_response_items if pr.get("source_prompt_packet_id") in linked_prompt_ids]
    linked_provider_response_ids = {pr.get("provider_response_id", "") for pr in linked_provider_responses}

    linked_response_reviews = [rr for rr in response_review_items if rr.get("source_provider_response_id") in linked_provider_response_ids]

    linked_sandbox_requests = [sr for sr in sandbox_request_items if sr.get("source_run_id") == safe_run_id]
    linked_sandbox_request_ids = {sr.get("sandbox_request_id", "") for sr in linked_sandbox_requests}

    from atlas_agent.research.provider_call_plan import iter_provider_call_plan_artifacts
    provider_call_plan_items = iter_provider_call_plan_artifacts(workspace_path, symbol=symbol)
    linked_provider_call_plans = [pcp for pcp in provider_call_plan_items if pcp.get("source_sandbox_request_id") in linked_sandbox_request_ids]
    linked_provider_call_plan_ids = {pcp.get("provider_call_plan_id", "") for pcp in linked_provider_call_plans}

    from atlas_agent.research.provider_execution_dry_run import iter_provider_execution_dry_run_artifacts
    provider_execution_dry_run_items = iter_provider_execution_dry_run_artifacts(workspace_path, symbol=symbol)
    linked_provider_execution_dry_runs = [ped for ped in provider_execution_dry_run_items if ped.get("source_provider_call_plan_id") in linked_provider_call_plan_ids]
    linked_provider_execution_dry_run_ids = {ped.get("provider_execution_dry_run_id", "") for ped in linked_provider_execution_dry_runs}

    from atlas_agent.research.provider_execution_state import iter_provider_execution_state_artifacts
    provider_execution_state_items = iter_provider_execution_state_artifacts(workspace_path, symbol=symbol)
    linked_provider_execution_states = [pes for pes in provider_execution_state_items if pes.get("source_provider_execution_dry_run_id") in linked_provider_execution_dry_run_ids]
    linked_provider_execution_state_ids = {pes.get("provider_execution_state_id", "") for pes in linked_provider_execution_states}

    from atlas_agent.research.provider_execution_audit_packet import iter_provider_execution_audit_packet_artifacts
    provider_execution_audit_packet_items = iter_provider_execution_audit_packet_artifacts(workspace_path, symbol=symbol)
    linked_provider_execution_audit_packets = [peap for peap in provider_execution_audit_packet_items if peap.get("source_provider_execution_state_id") in linked_provider_execution_state_ids]
    linked_audit_packet_ids = {peap.get("provider_execution_audit_packet_id", "") for peap in linked_provider_execution_audit_packets}

    from atlas_agent.research.provider_execution_readiness_report import iter_provider_execution_readiness_report_artifacts
    provider_execution_readiness_report_items = iter_provider_execution_readiness_report_artifacts(workspace_path, symbol=symbol)
    linked_provider_execution_readiness_reports = [perr for perr in provider_execution_readiness_report_items if perr.get("source_provider_execution_audit_packet_id") in linked_audit_packet_ids]
    linked_readiness_report_ids = {perr.get("provider_execution_readiness_report_id", "") for perr in linked_provider_execution_readiness_reports}

    from atlas_agent.research.provider_preflight_freeze import iter_provider_preflight_freeze_artifacts
    provider_preflight_freeze_items = iter_provider_preflight_freeze_artifacts(workspace_path, symbol=symbol)
    linked_provider_preflight_freezes = [ppf for ppf in provider_preflight_freeze_items if ppf.get("source_provider_execution_readiness_report_id") in linked_readiness_report_ids]
    linked_freeze_ids = {ppf.get("provider_preflight_freeze_id", "") for ppf in linked_provider_preflight_freezes}

    from atlas_agent.research.provider_opt_in_policy import iter_provider_opt_in_policy_artifacts
    provider_opt_in_policy_items = iter_provider_opt_in_policy_artifacts(workspace_path, symbol=symbol)
    linked_provider_opt_in_policies = [pop for pop in provider_opt_in_policy_items if pop.get("source_provider_preflight_freeze_id") in linked_freeze_ids]
    linked_policy_ids = {pop.get("provider_opt_in_policy_id", "") for pop in linked_provider_opt_in_policies}

    from atlas_agent.research.provider_credential_boundary import iter_provider_credential_boundary_artifacts
    provider_credential_boundary_items = iter_provider_credential_boundary_artifacts(workspace_path, symbol=symbol)
    linked_provider_credential_boundaries = [pcb for pcb in provider_credential_boundary_items if pcb.get("source_provider_opt_in_policy_id") in linked_policy_ids]
    linked_credential_boundary_ids = {pcb.get("provider_credential_boundary_id", "") for pcb in linked_provider_credential_boundaries}

    from atlas_agent.research.provider_outbound_payload_preview import iter_provider_outbound_payload_preview_artifacts
    provider_outbound_payload_preview_items = iter_provider_outbound_payload_preview_artifacts(workspace_path, symbol=symbol)
    linked_provider_outbound_payload_previews = [pp for pp in provider_outbound_payload_preview_items if pp.get("source_provider_credential_boundary_id") in linked_credential_boundary_ids]
    linked_payload_preview_ids = {pp.get("provider_outbound_payload_preview_id", "") for pp in linked_provider_outbound_payload_previews}

    from atlas_agent.research.provider_response_intake_policy import iter_provider_response_intake_policy_artifacts
    provider_response_intake_policy_items = iter_provider_response_intake_policy_artifacts(workspace_path, symbol=symbol)
    linked_provider_response_intake_policies = [pip for pip in provider_response_intake_policy_items if pip.get("source_provider_outbound_payload_preview_id") in linked_payload_preview_ids]
    linked_intake_policy_ids = {pip.get("provider_response_intake_policy_id", "") for pip in linked_provider_response_intake_policies}

    from atlas_agent.research.provider_request_response_pairing import iter_provider_request_response_pairing_artifacts
    provider_request_response_pairing_items = iter_provider_request_response_pairing_artifacts(workspace_path, symbol=symbol)
    linked_provider_request_response_pairings = [prrp for prrp in provider_request_response_pairing_items if prrp.get("source_provider_response_intake_policy_id") in linked_intake_policy_ids]
    linked_pairing_ids = {prrp.get("provider_request_response_pairing_id", "") for prrp in linked_provider_request_response_pairings}

    from atlas_agent.research.provider_response_schema_contract import iter_provider_response_schema_contract_artifacts
    provider_response_schema_contract_items = iter_provider_response_schema_contract_artifacts(workspace_path, symbol=symbol)
    linked_provider_response_schema_contracts = [prsc for prsc in provider_response_schema_contract_items if prsc.get("source_provider_request_response_pairing_id") in linked_pairing_ids]
    linked_schema_contract_ids = {prsc.get("provider_response_schema_contract_id", "") for prsc in linked_provider_response_schema_contracts}

    from atlas_agent.research.provider_response_review_result import iter_provider_response_review_result_artifacts
    provider_response_review_result_items = iter_provider_response_review_result_artifacts(workspace_path, symbol=symbol)
    linked_provider_response_review_results = [prrr for prrr in provider_response_review_result_items if prrr.get("source_provider_response_schema_contract_id") in linked_schema_contract_ids]
    linked_review_result_ids = {prrr.get("provider_response_review_result_id", "") for prrr in linked_provider_response_review_results}

    from atlas_agent.research.provider_execution_unlock_state import iter_provider_execution_unlock_state_artifacts
    provider_execution_unlock_state_items = iter_provider_execution_unlock_state_artifacts(workspace_path, symbol=symbol)
    linked_provider_execution_unlock_states = [pues for pues in provider_execution_unlock_state_items if pues.get("source_provider_response_review_result_id") in linked_review_result_ids]

    from atlas_agent.research.provider_adapter_interface_contract import iter_provider_adapter_interface_contract_artifacts
    provider_adapter_interface_contract_items = iter_provider_adapter_interface_contract_artifacts(workspace_path, symbol=symbol)
    linked_provider_execution_unlock_state_ids = {pues.get("provider_execution_unlock_state_id", "") for pues in linked_provider_execution_unlock_states}
    linked_provider_adapter_interface_contracts = [paic for paic in provider_adapter_interface_contract_items if paic.get("source_provider_execution_unlock_state_id") in linked_provider_execution_unlock_state_ids]
    linked_provider_adapter_interface_contract_ids = {paic.get("provider_adapter_interface_contract_id", "") for paic in linked_provider_adapter_interface_contracts}

    from atlas_agent.research.provider_mock_response_simulation import iter_provider_mock_response_simulation_artifacts
    provider_mock_response_simulation_items = iter_provider_mock_response_simulation_artifacts(workspace_path, symbol=symbol)
    linked_provider_mock_response_simulations = [pmrs for pmrs in provider_mock_response_simulation_items if pmrs.get("source_provider_adapter_interface_contract_id") in linked_provider_adapter_interface_contract_ids]
    linked_provider_mock_response_simulation_ids = {pmrs.get("provider_mock_response_simulation_id", "") for pmrs in linked_provider_mock_response_simulations}

    from atlas_agent.research.provider_mock_response_import_candidate import iter_provider_mock_response_import_candidate_artifacts
    provider_mock_response_import_candidate_items = iter_provider_mock_response_import_candidate_artifacts(workspace_path, symbol=symbol)
    linked_provider_mock_response_import_candidates = [pmrc for pmrc in provider_mock_response_import_candidate_items if pmrc.get("source_provider_mock_response_simulation_id") in linked_provider_mock_response_simulation_ids]
    linked_provider_mock_response_import_candidate_ids = {pmrc.get("provider_mock_response_import_candidate_id", "") for pmrc in linked_provider_mock_response_import_candidates}

    from atlas_agent.research.provider_mock_response_review_sandbox import iter_provider_mock_response_review_sandbox_artifacts
    provider_mock_response_review_sandbox_items = iter_provider_mock_response_review_sandbox_artifacts(workspace_path, symbol=symbol)
    linked_provider_mock_response_review_sandboxes = [pmrsb for pmrsb in provider_mock_response_review_sandbox_items if pmrsb.get("source_provider_mock_response_import_candidate_id") in linked_provider_mock_response_import_candidate_ids]
    linked_provider_mock_response_review_sandbox_ids = {pmrsb.get("provider_mock_response_review_sandbox_id", "") for pmrsb in linked_provider_mock_response_review_sandboxes}

    from atlas_agent.research.provider_mock_response_trust_decision_blocker import iter_provider_mock_response_trust_decision_blocker_artifacts
    provider_mock_response_trust_decision_blocker_items = iter_provider_mock_response_trust_decision_blocker_artifacts(workspace_path, symbol=symbol)
    linked_provider_mock_response_trust_decision_blockers = [pmtb for pmtb in provider_mock_response_trust_decision_blocker_items if pmtb.get("source_provider_mock_response_review_sandbox_id") in linked_provider_mock_response_review_sandbox_ids]

    from atlas_agent.research.provider_mock_response_final_safety_seal import iter_provider_mock_response_final_safety_seal_artifacts
    provider_mock_response_final_safety_seal_items = iter_provider_mock_response_final_safety_seal_artifacts(workspace_path, symbol=symbol)
    linked_provider_mock_response_final_safety_seals = [pmfs for pmfs in provider_mock_response_final_safety_seal_items if pmfs.get("source_trust_decision_blocker_id") in {pmtb.get("provider_mock_response_trust_decision_blocker_id", "") for pmtb in linked_provider_mock_response_trust_decision_blockers}]

    # Build workflow status
    workflow_status = {
        "research": True,
        "plans": len(linked_plans) > 0,
        "verifications": len(linked_verifications) > 0,
        "evaluations": len(linked_evaluations) > 0,
        "prompts": len(linked_prompts) > 0,
        "provider_responses": len(linked_provider_responses) > 0,
        "response_reviews": len(linked_response_reviews) > 0,
        "sandbox_requests": len(linked_sandbox_requests) > 0,
        "provider_call_plans": len(linked_provider_call_plans) > 0,
        "provider_execution_dry_runs": len(linked_provider_execution_dry_runs) > 0,
        "provider_execution_states": len(linked_provider_execution_states) > 0,
        "provider_execution_audit_packets": len(linked_provider_execution_audit_packets) > 0,
        "provider_execution_readiness_reports": len(linked_provider_execution_readiness_reports) > 0,
        "provider_preflight_freezes": len(linked_provider_preflight_freezes) > 0,
        "provider_opt_in_policies": len(linked_provider_opt_in_policies) > 0,
        "provider_credential_boundaries": len(linked_provider_credential_boundaries) > 0,
        "provider_outbound_payload_previews": len(linked_provider_outbound_payload_previews) > 0,
        "provider_response_intake_policies": len(linked_provider_response_intake_policies) > 0,
        "provider_request_response_pairings": len(linked_provider_request_response_pairings) > 0,
        "provider_response_schema_contracts": len(linked_provider_response_schema_contracts) > 0,
        "provider_response_review_results": len(linked_provider_response_review_results) > 0,
        "provider_execution_unlock_states": len(linked_provider_execution_unlock_states) > 0,
        "provider_adapter_interface_contracts": len(linked_provider_adapter_interface_contracts) > 0,
        "provider_mock_response_simulations": len(linked_provider_mock_response_simulations) > 0,
        "provider_mock_response_import_candidates": len(linked_provider_mock_response_import_candidates) > 0,
        "provider_mock_response_review_sandboxes": len(linked_provider_mock_response_review_sandboxes) > 0,
        "provider_mock_response_trust_decision_blockers": len(linked_provider_mock_response_trust_decision_blockers) > 0,
        "provider_mock_response_final_safety_seals": len(linked_provider_mock_response_final_safety_seals) > 0,
    }

    artifact_counts = {
        "research": 1,
        "plans": len(linked_plans),
        "verifications": len(linked_verifications),
        "evaluations": len(linked_evaluations),
        "prompts": len(linked_prompts),
        "provider_responses": len(linked_provider_responses),
        "response_reviews": len(linked_response_reviews),
        "sandbox_requests": len(linked_sandbox_requests),
        "provider_call_plans": len(linked_provider_call_plans),
        "provider_execution_dry_runs": len(linked_provider_execution_dry_runs),
        "provider_execution_states": len(linked_provider_execution_states),
        "provider_execution_audit_packets": len(linked_provider_execution_audit_packets),
        "provider_execution_readiness_reports": len(linked_provider_execution_readiness_reports),
        "provider_preflight_freezes": len(linked_provider_preflight_freezes),
        "provider_opt_in_policies": len(linked_provider_opt_in_policies),
        "provider_credential_boundaries": len(linked_provider_credential_boundaries),
        "provider_outbound_payload_previews": len(linked_provider_outbound_payload_previews),
        "provider_response_intake_policies": len(linked_provider_response_intake_policies),
        "provider_request_response_pairings": len(linked_provider_request_response_pairings),
        "provider_response_schema_contracts": len(linked_provider_response_schema_contracts),
        "provider_response_review_results": len(linked_provider_response_review_results),
        "provider_execution_unlock_states": len(linked_provider_execution_unlock_states),
        "provider_adapter_interface_contracts": len(linked_provider_adapter_interface_contracts),
        "provider_mock_response_simulations": len(linked_provider_mock_response_simulations),
        "provider_mock_response_import_candidates": len(linked_provider_mock_response_import_candidates),
        "provider_mock_response_review_sandboxes": len(linked_provider_mock_response_review_sandboxes),
        "provider_mock_response_trust_decision_blockers": len(linked_provider_mock_response_trust_decision_blockers),
        "provider_mock_response_final_safety_seals": len(linked_provider_mock_response_final_safety_seals),
    }

    # Build linked_artifacts with relative paths only
    linked_artifacts: list[dict[str, Any]] = []
    for p in linked_plans:
        linked_artifacts.append({
            "type": "plan",
            "id": p.get("plan_id", ""),
            "artifact_path": p.get("artifact_path", ""),
        })
    for v in linked_verifications:
        linked_artifacts.append({
            "type": "verification",
            "id": v.get("verification_id", ""),
            "recommendation": v.get("recommendation", ""),
            "artifact_path": v.get("artifact_path", ""),
        })
    for e in linked_evaluations:
        linked_artifacts.append({
            "type": "evaluation",
            "id": e.get("evaluation_id", ""),
            "recommendation": e.get("recommendation", ""),
            "artifact_path": e.get("artifact_path", ""),
        })
    for p in linked_prompts:
        linked_artifacts.append({
            "type": "prompt",
            "id": p.get("prompt_packet_id", ""),
            "artifact_path": p.get("artifact_path", ""),
        })
    for pr in linked_provider_responses:
        linked_artifacts.append({
            "type": "provider_response",
            "id": pr.get("provider_response_id", ""),
            "provider": pr.get("provider", "unknown"),
            "recommendation": pr.get("recommendation", ""),
            "artifact_path": pr.get("artifact_path", ""),
        })
    for rr in linked_response_reviews:
        linked_artifacts.append({
            "type": "response_review",
            "id": rr.get("response_review_id", ""),
            "provider": rr.get("provider", "unknown"),
            "recommendation": rr.get("recommendation", ""),
            "artifact_path": rr.get("artifact_path", ""),
        })
    for sr in linked_sandbox_requests:
        linked_artifacts.append({
            "type": "sandbox_request",
            "id": sr.get("sandbox_request_id", ""),
            "artifact_path": sr.get("artifact_path", ""),
            "recommendation": sr.get("recommendation", ""),
        })
    for pcp in linked_provider_call_plans:
        linked_artifacts.append({
            "type": "provider_call_plan",
            "id": pcp.get("provider_call_plan_id", ""),
            "artifact_path": pcp.get("artifact_path", ""),
            "provider_id": pcp.get("provider_id", ""),
            "model_id": pcp.get("model_id", ""),
        })
    for ped in linked_provider_execution_dry_runs:
        linked_artifacts.append({
            "type": "provider_execution_dry_run",
            "id": ped.get("provider_execution_dry_run_id", ""),
            "artifact_path": ped.get("artifact_path", ""),
            "provider_id": ped.get("provider_id", ""),
            "model_id": ped.get("model_id", ""),
        })
    for pes in linked_provider_execution_states:
        linked_artifacts.append({
            "type": "provider_execution_state",
            "id": pes.get("provider_execution_state_id", ""),
            "artifact_path": pes.get("artifact_path", ""),
            "provider_id": pes.get("provider_id", ""),
            "model_id": pes.get("model_id", ""),
            "state": pes.get("state", ""),
        })
    for peap in linked_provider_execution_audit_packets:
        linked_artifacts.append({
            "type": "provider_execution_audit_packet",
            "id": peap.get("provider_execution_audit_packet_id", ""),
            "artifact_path": peap.get("artifact_path", ""),
            "provider_id": peap.get("provider_id", ""),
            "model_id": peap.get("model_id", ""),
        })
    for perr in linked_provider_execution_readiness_reports:
        linked_artifacts.append({
            "type": "provider_execution_readiness_report",
            "id": perr.get("provider_execution_readiness_report_id", ""),
            "artifact_path": perr.get("artifact_path", ""),
            "readiness_status": perr.get("readiness_status", ""),
            "readiness_score": perr.get("readiness_score", 0),
            "chain_health": perr.get("chain_health", ""),
        })
    for ppf in linked_provider_preflight_freezes:
        linked_artifacts.append({
            "type": "provider_preflight_freeze",
            "id": ppf.get("provider_preflight_freeze_id", ""),
            "artifact_path": ppf.get("artifact_path", ""),
            "freeze_status": ppf.get("freeze_status", ""),
            "freeze_recommendation": ppf.get("freeze_recommendation", ""),
            "readiness_score": ppf.get("readiness_score", 0),
            "chain_health": ppf.get("chain_health", ""),
        })
    for pop in linked_provider_opt_in_policies:
        linked_artifacts.append({
            "type": "provider_opt_in_policy",
            "id": pop.get("provider_opt_in_policy_id", ""),
            "artifact_path": pop.get("artifact_path", ""),
            "policy_status": pop.get("policy_status", ""),
            "policy_scope": pop.get("policy_scope", ""),
            "opt_in_state": pop.get("opt_in_state", ""),
        })
    for pcb in linked_provider_credential_boundaries:
        linked_artifacts.append({
            "type": "provider_credential_boundary",
            "id": pcb.get("provider_credential_boundary_id", ""),
            "artifact_path": pcb.get("artifact_path", ""),
            "credential_boundary_status": pcb.get("credential_boundary_status", ""),
            "credential_boundary_scope": pcb.get("credential_boundary_scope", ""),
            "credential_loading_state": pcb.get("credential_loading_state", ""),
        })
    for pp in linked_provider_outbound_payload_previews:
        linked_artifacts.append({
            "type": "provider_outbound_payload_preview",
            "id": pp.get("provider_outbound_payload_preview_id", ""),
            "artifact_path": pp.get("artifact_path", ""),
            "payload_preview_status": pp.get("payload_preview_status", ""),
            "payload_preview_scope": pp.get("payload_preview_scope", ""),
            "provider_id": pp.get("provider_id", ""),
            "model_id": pp.get("model_id", ""),
        })
    for pip in linked_provider_response_intake_policies:
        linked_artifacts.append({
            "type": "provider_response_intake_policy",
            "id": pip.get("provider_response_intake_policy_id", ""),
            "artifact_path": pip.get("artifact_path", ""),
            "response_intake_policy_status": pip.get("response_intake_policy_status", ""),
            "response_intake_policy_scope": pip.get("response_intake_policy_scope", ""),
            "provider_id": pip.get("provider_id", ""),
            "model_id": pip.get("model_id", ""),
        })
    for prrp in linked_provider_request_response_pairings:
        linked_artifacts.append({
            "type": "provider_request_response_pairing",
            "id": prrp.get("provider_request_response_pairing_id", ""),
            "artifact_path": prrp.get("artifact_path", ""),
            "pairing_status": prrp.get("pairing_status", ""),
            "pairing_state": prrp.get("pairing_state", ""),
            "provider_id": prrp.get("provider_id", ""),
            "model_id": prrp.get("model_id", ""),
        })
    for prsc in linked_provider_response_schema_contracts:
        linked_artifacts.append({
            "type": "provider_response_schema_contract",
            "id": prsc.get("provider_response_schema_contract_id", ""),
            "artifact_path": prsc.get("artifact_path", ""),
            "response_schema_status": prsc.get("response_schema_status", ""),
            "response_schema_state": prsc.get("response_schema_state", ""),
            "provider_id": prsc.get("provider_id", ""),
            "model_id": prsc.get("model_id", ""),
        })
    for prrr in linked_provider_response_review_results:
        linked_artifacts.append({
            "type": "provider_response_review_result",
            "id": prrr.get("provider_response_review_result_id", ""),
            "artifact_path": prrr.get("artifact_path", ""),
            "review_result_status": prrr.get("review_result_status", ""),
            "review_result_state": prrr.get("review_result_state", ""),
            "review_decision": prrr.get("review_decision", ""),
            "provider_id": prrr.get("provider_id", ""),
            "model_id": prrr.get("model_id", ""),
        })
    for pues in linked_provider_execution_unlock_states:
        linked_artifacts.append({
            "type": "provider_execution_unlock_state",
            "id": pues.get("provider_execution_unlock_state_id", ""),
            "artifact_path": pues.get("artifact_path", ""),
            "unlock_state_status": pues.get("unlock_state_status", ""),
            "unlock_state": pues.get("unlock_state", ""),
            "current_state": pues.get("current_state", ""),
            "provider_id": pues.get("provider_id", ""),
            "model_id": pues.get("model_id", ""),
        })
    for paic in linked_provider_adapter_interface_contracts:
        linked_artifacts.append({
            "type": "provider_adapter_interface_contract",
            "id": paic.get("provider_adapter_interface_contract_id", ""),
            "artifact_path": paic.get("artifact_path", ""),
            "adapter_contract_status": paic.get("adapter_contract_status", ""),
            "adapter_state": paic.get("adapter_state", ""),
            "provider_id": paic.get("provider_id", ""),
            "model_id": paic.get("model_id", ""),
        })
    for pmrs in linked_provider_mock_response_simulations:
        linked_artifacts.append({
            "type": "provider_mock_response_simulation",
            "id": pmrs.get("provider_mock_response_simulation_id", ""),
            "artifact_path": pmrs.get("artifact_path", ""),
            "mock_simulation_status": pmrs.get("mock_simulation_status", ""),
            "mock_simulation_state": pmrs.get("mock_simulation_state", ""),
            "provider_id": pmrs.get("provider_id", ""),
            "model_id": pmrs.get("model_id", ""),
        })
    for pmrc in linked_provider_mock_response_import_candidates:
        linked_artifacts.append({
            "type": "provider_mock_response_import_candidate",
            "id": pmrc.get("provider_mock_response_import_candidate_id", ""),
            "artifact_path": pmrc.get("artifact_path", ""),
            "mock_import_candidate_status": pmrc.get("mock_import_candidate_status", ""),
            "mock_import_candidate_state": pmrc.get("mock_import_candidate_state", ""),
            "provider_id": pmrc.get("provider_id", ""),
            "model_id": pmrc.get("model_id", ""),
        })
    for pmrsb in linked_provider_mock_response_review_sandboxes:
        linked_artifacts.append({
            "type": "provider_mock_response_review_sandbox",
            "id": pmrsb.get("provider_mock_response_review_sandbox_id", ""),
            "artifact_path": pmrsb.get("artifact_path", ""),
            "mock_review_sandbox_status": pmrsb.get("mock_review_sandbox_status", ""),
            "mock_review_sandbox_state": pmrsb.get("mock_review_sandbox_state", ""),
            "provider_id": pmrsb.get("provider_id", ""),
            "model_id": pmrsb.get("model_id", ""),
        })
    for pmtb in linked_provider_mock_response_trust_decision_blockers:
        linked_artifacts.append({
            "type": "provider_mock_response_trust_decision_blocker",
            "id": pmtb.get("provider_mock_response_trust_decision_blocker_id", ""),
            "artifact_path": pmtb.get("artifact_path", ""),
            "trust_decision_blocker_status": pmtb.get("trust_decision_blocker_status", ""),
            "trust_decision_blocker_state": pmtb.get("trust_decision_blocker_state", ""),
            "provider_id": pmtb.get("provider_id", ""),
            "model_id": pmtb.get("model_id", ""),
        })
    for pmfs in linked_provider_mock_response_final_safety_seals:
        linked_artifacts.append({
            "type": "provider_mock_response_final_safety_seal",
            "id": pmfs.get("provider_mock_response_final_safety_seal_id", ""),
            "artifact_path": pmfs.get("artifact_path", ""),
            "final_safety_seal_status": pmfs.get("final_safety_seal_status", ""),
            "final_safety_seal_state": pmfs.get("final_safety_seal_state", ""),
            "provider_id": pmfs.get("provider_id", ""),
            "model_id": pmfs.get("model_id", ""),
        })

    # Build summaries (bounded, no full bodies)
    summaries: dict[str, Any] = {
        "research": {
            "run_id": safe_run_id,
            "symbol": symbol,
            "mode": "paper",
        },
    }
    if linked_plans:
        summaries["plan"] = {
            "plan_count": len(linked_plans),
            "plan_ids": [p.get("plan_id", "") for p in linked_plans],
        }
    if linked_verifications:
        passed = sum(1 for v in linked_verifications if "ready" in v.get("recommendation", ""))
        summaries["verification"] = {
            "verification_count": len(linked_verifications),
            "recommendations": [v.get("recommendation", "") for v in linked_verifications],
        }
    if linked_evaluations:
        summaries["evaluation"] = {
            "evaluation_count": len(linked_evaluations),
            "recommendations": [e.get("recommendation", "") for e in linked_evaluations],
        }
    if linked_provider_responses:
        summaries["provider_response"] = {
            "response_count": len(linked_provider_responses),
            "recommendations": [pr.get("recommendation", "") for pr in linked_provider_responses],
        }
    if linked_response_reviews:
        summaries["response_review"] = {
            "review_count": len(linked_response_reviews),
            "recommendations": [rr.get("recommendation", "") for rr in linked_response_reviews],
        }
    if linked_provider_call_plans:
        summaries["provider_call_plan"] = {
            "plan_count": len(linked_provider_call_plans),
            "provider_ids": [pcp.get("provider_id", "") for pcp in linked_provider_call_plans],
            "model_ids": [pcp.get("model_id", "") for pcp in linked_provider_call_plans],
        }
    if linked_provider_execution_dry_runs:
        summaries["provider_execution_dry_run"] = {
            "dry_run_count": len(linked_provider_execution_dry_runs),
            "provider_ids": [ped.get("provider_id", "") for ped in linked_provider_execution_dry_runs],
            "model_ids": [ped.get("model_id", "") for ped in linked_provider_execution_dry_runs],
        }
    if linked_provider_execution_states:
        summaries["provider_execution_state"] = {
            "state_count": len(linked_provider_execution_states),
            "states": [pes.get("state", "") for pes in linked_provider_execution_states],
            "provider_ids": [pes.get("provider_id", "") for pes in linked_provider_execution_states],
            "model_ids": [pes.get("model_id", "") for pes in linked_provider_execution_states],
        }
    if linked_provider_execution_audit_packets:
        summaries["provider_execution_audit_packet"] = {
            "audit_packet_count": len(linked_provider_execution_audit_packets),
            "audit_statuses": [peap.get("audit_status", "") for peap in linked_provider_execution_audit_packets],
            "execution_statuses": [peap.get("execution_status", "") for peap in linked_provider_execution_audit_packets],
            "provider_ids": [peap.get("provider_id", "") for peap in linked_provider_execution_audit_packets],
            "model_ids": [peap.get("model_id", "") for peap in linked_provider_execution_audit_packets],
        }
    if linked_provider_execution_readiness_reports:
        summaries["provider_execution_readiness_report"] = {
            "readiness_report_count": len(linked_provider_execution_readiness_reports),
            "readiness_statuses": [perr.get("readiness_status", "") for perr in linked_provider_execution_readiness_reports],
            "readiness_scores": [perr.get("readiness_score", 0) for perr in linked_provider_execution_readiness_reports],
            "chain_health_values": [perr.get("chain_health", "") for perr in linked_provider_execution_readiness_reports],
        }
    if linked_provider_preflight_freezes:
        summaries["provider_preflight_freeze"] = {
            "freeze_count": len(linked_provider_preflight_freezes),
            "freeze_statuses": [ppf.get("freeze_status", "") for ppf in linked_provider_preflight_freezes],
            "freeze_recommendations": [ppf.get("freeze_recommendation", "") for ppf in linked_provider_preflight_freezes],
            "readiness_scores": [ppf.get("readiness_score", 0) for ppf in linked_provider_preflight_freezes],
            "chain_health_values": [ppf.get("chain_health", "") for ppf in linked_provider_preflight_freezes],
        }
    if linked_provider_opt_in_policies:
        summaries["provider_opt_in_policy"] = {
            "policy_count": len(linked_provider_opt_in_policies),
            "policy_statuses": [pop.get("policy_status", "") for pop in linked_provider_opt_in_policies],
            "policy_scopes": [pop.get("policy_scope", "") for pop in linked_provider_opt_in_policies],
            "opt_in_states": [pop.get("opt_in_state", "") for pop in linked_provider_opt_in_policies],
        }
    if linked_provider_credential_boundaries:
        summaries["provider_credential_boundary"] = {
            "boundary_count": len(linked_provider_credential_boundaries),
            "boundary_statuses": [pcb.get("credential_boundary_status", "") for pcb in linked_provider_credential_boundaries],
            "boundary_scopes": [pcb.get("credential_boundary_scope", "") for pcb in linked_provider_credential_boundaries],
            "credential_loading_states": [pcb.get("credential_loading_state", "") for pcb in linked_provider_credential_boundaries],
        }
    if linked_provider_outbound_payload_previews:
        summaries["provider_outbound_payload_preview"] = {
            "preview_count": len(linked_provider_outbound_payload_previews),
            "payload_preview_statuses": [pp.get("payload_preview_status", "") for pp in linked_provider_outbound_payload_previews],
            "payload_preview_scopes": [pp.get("payload_preview_scope", "") for pp in linked_provider_outbound_payload_previews],
            "provider_ids": [pp.get("provider_id", "") for pp in linked_provider_outbound_payload_previews],
            "model_ids": [pp.get("model_id", "") for pp in linked_provider_outbound_payload_previews],
        }
    if linked_provider_response_intake_policies:
        summaries["provider_response_intake_policy"] = {
            "policy_count": len(linked_provider_response_intake_policies),
            "response_intake_policy_statuses": [pip.get("response_intake_policy_status", "") for pip in linked_provider_response_intake_policies],
            "response_intake_policy_scopes": [pip.get("response_intake_policy_scope", "") for pip in linked_provider_response_intake_policies],
            "provider_ids": [pip.get("provider_id", "") for pip in linked_provider_response_intake_policies],
            "model_ids": [pip.get("model_id", "") for pip in linked_provider_response_intake_policies],
        }
    if linked_provider_request_response_pairings:
        summaries["provider_request_response_pairing"] = {
            "pairing_count": len(linked_provider_request_response_pairings),
            "pairing_statuses": [prrp.get("pairing_status", "") for prrp in linked_provider_request_response_pairings],
            "pairing_states": [prrp.get("pairing_state", "") for prrp in linked_provider_request_response_pairings],
            "provider_ids": [prrp.get("provider_id", "") for prrp in linked_provider_request_response_pairings],
            "model_ids": [prrp.get("model_id", "") for prrp in linked_provider_request_response_pairings],
        }
    if linked_provider_response_schema_contracts:
        summaries["provider_response_schema_contract"] = {
            "contract_count": len(linked_provider_response_schema_contracts),
            "response_schema_statuses": [prsc.get("response_schema_status", "") for prsc in linked_provider_response_schema_contracts],
            "response_schema_states": [prsc.get("response_schema_state", "") for prsc in linked_provider_response_schema_contracts],
            "provider_ids": [prsc.get("provider_id", "") for prsc in linked_provider_response_schema_contracts],
            "model_ids": [prsc.get("model_id", "") for prsc in linked_provider_response_schema_contracts],
            "manual_review_gate_open": False,
            "future_response_artifact_present": False,
        }
    if linked_provider_response_review_results:
        summaries["provider_response_review_result"] = {
            "review_result_count": len(linked_provider_response_review_results),
            "review_result_statuses": [prrr.get("review_result_status", "") for prrr in linked_provider_response_review_results],
            "review_result_states": [prrr.get("review_result_state", "") for prrr in linked_provider_response_review_results],
            "review_decisions": [prrr.get("review_decision", "") for prrr in linked_provider_response_review_results],
            "provider_ids": [prrr.get("provider_id", "") for prrr in linked_provider_response_review_results],
            "model_ids": [prrr.get("model_id", "") for prrr in linked_provider_response_review_results],
        }
    if linked_provider_execution_unlock_states:
        summaries["provider_execution_unlock_state"] = {
            "unlock_state_count": len(linked_provider_execution_unlock_states),
            "unlock_state_statuses": [pues.get("unlock_state_status", "") for pues in linked_provider_execution_unlock_states],
            "unlock_states": [pues.get("unlock_state", "") for pues in linked_provider_execution_unlock_states],
            "current_states": [pues.get("current_state", "") for pues in linked_provider_execution_unlock_states],
            "provider_ids": [pues.get("provider_id", "") for pues in linked_provider_execution_unlock_states],
            "model_ids": [pues.get("model_id", "") for pues in linked_provider_execution_unlock_states],
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }
    if linked_provider_adapter_interface_contracts:
        summaries["provider_adapter_interface_contract"] = {
            "contract_count": len(linked_provider_adapter_interface_contracts),
            "adapter_contract_statuses": [paic.get("adapter_contract_status", "") for paic in linked_provider_adapter_interface_contracts],
            "adapter_states": [paic.get("adapter_state", "") for paic in linked_provider_adapter_interface_contracts],
            "provider_ids": [paic.get("provider_id", "") for paic in linked_provider_adapter_interface_contracts],
            "model_ids": [paic.get("model_id", "") for paic in linked_provider_adapter_interface_contracts],
            "adapter_present": False,
            "adapter_enabled": False,
            "real_provider_adapter_implemented": False,
        }
    if linked_provider_mock_response_simulations:
        summaries["provider_mock_response_simulation"] = {
            "simulation_count": len(linked_provider_mock_response_simulations),
            "mock_simulation_statuses": [pmrs.get("mock_simulation_status", "") for pmrs in linked_provider_mock_response_simulations],
            "mock_simulation_states": [pmrs.get("mock_simulation_state", "") for pmrs in linked_provider_mock_response_simulations],
            "provider_ids": [pmrs.get("provider_id", "") for pmrs in linked_provider_mock_response_simulations],
            "model_ids": [pmrs.get("model_id", "") for pmrs in linked_provider_mock_response_simulations],
            "mock_adapter_used": True,
            "mock_response_simulated": True,
            "mock_only": True,
            "real_provider_request_sent": False,
            "real_provider_response_received": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }
    if linked_provider_mock_response_review_sandboxes:
        summaries["provider_mock_response_review_sandbox"] = {
            "sandbox_count": len(linked_provider_mock_response_review_sandboxes),
            "mock_review_sandbox_statuses": [pmrsb.get("mock_review_sandbox_status", "") for pmrsb in linked_provider_mock_response_review_sandboxes],
            "mock_review_sandbox_states": [pmrsb.get("mock_review_sandbox_state", "") for pmrsb in linked_provider_mock_response_review_sandboxes],
            "provider_ids": [pmrsb.get("provider_id", "") for pmrsb in linked_provider_mock_response_review_sandboxes],
            "model_ids": [pmrsb.get("model_id", "") for pmrsb in linked_provider_mock_response_review_sandboxes],
            "mock_review_sandbox_recorded": True,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }
    if linked_provider_mock_response_trust_decision_blockers:
        summaries["provider_mock_response_trust_decision_blocker"] = {
            "blocker_count": len(linked_provider_mock_response_trust_decision_blockers),
            "trust_decision_blocker_statuses": [pmtb.get("trust_decision_blocker_status", "") for pmtb in linked_provider_mock_response_trust_decision_blockers],
            "trust_decision_blocker_states": [pmtb.get("trust_decision_blocker_state", "") for pmtb in linked_provider_mock_response_trust_decision_blockers],
            "provider_ids": [pmtb.get("provider_id", "") for pmtb in linked_provider_mock_response_trust_decision_blockers],
            "model_ids": [pmtb.get("model_id", "") for pmtb in linked_provider_mock_response_trust_decision_blockers],
            "trust_decision_blocker_recorded": True,
            "trust_blocker_active": True,
            "mock_only": True,
            "sandbox_only": True,
            "trust_decision_present": False,
            "trust_decision_granted": False,
            "trust_decision_explicitly_blocked": True,
            "trust_upgrade_performed": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    # Safety summary
    safety_summary = {
        "all_local": True,
        "no_network_calls": True,
        "no_api_keys_read": True,
        "paper_only": True,
    }

    # Missing links
    missing_links: list[str] = []
    if not linked_plans:
        missing_links.append("no_plan")
    if not linked_verifications:
        missing_links.append("no_verification")
    if not linked_evaluations:
        missing_links.append("no_evaluation")
    if not linked_prompts:
        missing_links.append("no_prompt_packet")
    if not linked_provider_responses:
        missing_links.append("no_provider_response")
    if not linked_response_reviews:
        missing_links.append("no_response_review")
    if not linked_sandbox_requests:
        missing_links.append("no_sandbox_request")
    if not linked_provider_call_plans:
        missing_links.append("no_provider_call_plan")
    if not linked_provider_execution_dry_runs:
        missing_links.append("no_provider_execution_dry_run")
    if not linked_provider_execution_states:
        missing_links.append("no_provider_execution_state")
    if not linked_provider_execution_audit_packets:
        missing_links.append("no_provider_execution_audit_packet")
    if not linked_provider_execution_readiness_reports:
        missing_links.append("no_provider_execution_readiness_report")
    if not linked_provider_preflight_freezes:
        missing_links.append("no_provider_preflight_freeze")
    if not linked_provider_opt_in_policies:
        missing_links.append("no_provider_opt_in_policy")
    if not linked_provider_credential_boundaries:
        missing_links.append("no_provider_credential_boundary")
    if not linked_provider_mock_response_simulations:
        missing_links.append("no_provider_mock_response_simulation")
    if not linked_provider_mock_response_review_sandboxes:
        missing_links.append("no_provider_mock_response_review_sandbox")
    if not linked_provider_mock_response_trust_decision_blockers:
        missing_links.append("no_provider_mock_response_trust_decision_blocker")
    if not linked_provider_mock_response_final_safety_seals:
        missing_links.append("no_provider_mock_response_final_safety_seal")

    warnings: list[str] = []
    if missing_links:
        warnings.append("incomplete_chain")
    if not linked_provider_outbound_payload_previews:
        warnings.append("no_provider_outbound_payload_preview")
    if not linked_provider_response_intake_policies:
        warnings.append("no_provider_response_intake_policy")
    if not linked_provider_response_schema_contracts:
        warnings.append("no_provider_response_schema_contract")
    else:
        warnings.append("missing_future_response_artifact_expected")
    if not linked_provider_response_review_results:
        warnings.append("no_provider_response_review_result")
    if not linked_provider_execution_unlock_states:
        warnings.append("no_provider_execution_unlock_state")

    # Determine recommendation
    core_present = linked_plans and linked_prompts and linked_provider_responses and linked_response_reviews
    if core_present and not warnings:
        recommendation = "research_dossier_ready"
    else:
        recommendation = "manual_review_required"

    redaction_summary = {
        "redacted_fragments_count": 0,
    }

    artifact_path_rel = f".atlas/research/{symbol}/dossiers/{dossier_id}.json"

    artifact = DossierArtifact(
        dossier_id=dossier_id,
        source_run_id=safe_run_id,
        created_at=created_at,
        symbol=symbol,
        mode="paper",
        provider="deterministic-dossier",
        source_research_path=source_research_path,
        workflow_status=workflow_status,
        artifact_counts=artifact_counts,
        linked_artifacts=linked_artifacts,
        summaries=summaries,
        safety_summary=safety_summary,
        missing_links=missing_links,
        warnings=warnings,
        recommendation=recommendation,
        redaction_summary=redaction_summary,
        artifact_path=artifact_path_rel,
        metadata={
            "dossier_provider": "deterministic-dossier",
        },
    )

    # Persist
    dossiers_dir = workspace_path / RESEARCH_DIR / symbol / "dossiers"
    dossiers_dir.mkdir(parents=True, exist_ok=True)
    dossier_file = dossiers_dir / f"{dossier_id}.json"
    _write_dossier_safe_json(dossier_file, artifact)

    # Rebuild with final artifact_path
    artifact = DossierArtifact(
        dossier_id=artifact.dossier_id,
        source_run_id=artifact.source_run_id,
        created_at=artifact.created_at,
        symbol=artifact.symbol,
        mode=artifact.mode,
        provider=artifact.provider,
        source_research_path=artifact.source_research_path,
        workflow_status=artifact.workflow_status,
        artifact_counts=artifact.artifact_counts,
        linked_artifacts=artifact.linked_artifacts,
        summaries=artifact.summaries,
        safety_summary=artifact.safety_summary,
        missing_links=artifact.missing_links,
        warnings=artifact.warnings,
        recommendation=artifact.recommendation,
        redaction_summary=artifact.redaction_summary,
        artifact_path=dossier_file.relative_to(workspace_path).as_posix(),
        metadata=artifact.metadata,
    )

    result: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "dossier_id": artifact.dossier_id,
        "source_run_id": artifact.source_run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "source_research_path": artifact.source_research_path,
        "workflow_status": artifact.workflow_status,
        "artifact_counts": artifact.artifact_counts,
        "linked_artifacts": artifact.linked_artifacts,
        "summaries": artifact.summaries,
        "safety_summary": artifact.safety_summary,
        "missing_links": artifact.missing_links,
        "warnings": artifact.warnings,
        "recommendation": artifact.recommendation,
        "redaction_summary": artifact.redaction_summary,
        "metadata": artifact.metadata,
        "artifact_path": artifact.artifact_path,
    }
    result, _ = _sanitize_prompt_value(result)

    # Log safe event
    if event_logger is not None:
        payload = {
            "dossier_id": dossier_id,
            "source_run_id": safe_run_id,
            "symbol": symbol,
            "mode": "paper",
            "provider": "deterministic-dossier",
            "recommendation": recommendation,
            "artifact_path": artifact.artifact_path,
            "status": "created",
            "schema_version": artifact.schema_version,
            "artifact_counts": artifact_counts,
        }
        safe_payload, _ = _sanitize_prompt_value(payload)
        event_logger.write(
            "research_dossier_created",
            run_id=dossier_id,
            command="atlas research dossier",
            mode="paper",
            payload=safe_payload,
        )

    return result


def _write_dossier_safe_json(path: Path, artifact: DossierArtifact) -> None:
    data: dict[str, Any] = {
        "schema_version": artifact.schema_version,
        "dossier_id": artifact.dossier_id,
        "source_run_id": artifact.source_run_id,
        "created_at": artifact.created_at.isoformat(),
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "source_research_path": artifact.source_research_path,
        "workflow_status": artifact.workflow_status,
        "artifact_counts": artifact.artifact_counts,
        "linked_artifacts": artifact.linked_artifacts,
        "summaries": artifact.summaries,
        "safety_summary": artifact.safety_summary,
        "missing_links": artifact.missing_links,
        "warnings": artifact.warnings,
        "recommendation": artifact.recommendation,
        "redaction_summary": artifact.redaction_summary,
        "metadata": artifact.metadata,
        "artifact_path": artifact.artifact_path,
    }
    safe_data, _ = _sanitize_prompt_value(data)
    path.write_text(json.dumps(safe_data, indent=2, sort_keys=True), encoding="utf-8")


def _iter_dossier_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return dossier artifact metadata dicts, newest first."""
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "dossiers")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                d_dir = sym_dir / "dossiers"
                if d_dir.exists():
                    search_dirs.append(d_dir)

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
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append(
                {
                    "dossier_id": data.get("dossier_id", path.stem),
                    "source_run_id": data.get("source_run_id", ""),
                    "symbol": data.get("symbol", ""),
                    "recommendation": data.get("recommendation", ""),
                    "created_at": data.get("created_at", ""),
                    "artifact_path": rel_path,
                }
            )

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items
