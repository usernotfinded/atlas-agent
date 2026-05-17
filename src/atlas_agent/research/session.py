from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas_agent.events.log import EventLogger, generate_run_id
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
            # Skip unsupported schema versions safely in list mode
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
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
            # Skip unsupported schema versions safely in list mode
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
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
    # Fail closed on unsupported schema versions when loading full artifacts
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_research_artifact_schema")
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
    counts = {"research": 0, "plans": 0, "verifications": 0, "evaluations": 0, "prompts": 0, "provider_responses": 0}

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
        if expected_type == "plan" and "plans" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "verification" and "verifications" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "evaluation" and "evaluations" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "prompt" and "prompts" not in rel.split("/"):
            warnings.append({"code": "unexpected_artifact_location", "path": rel, "severity": "warning"})
        elif expected_type == "provider_response" and "provider_responses" not in rel.split("/"):
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

    # Track seen run IDs for orphan prompt detection
    for p in prompt_items:
        src = p.get("source_run_id", "")
        if src and src not in seen_run_ids:
            warnings.append({"code": "orphan_prompt", "path": p.get("artifact_path", ""), "severity": "warning"})

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
            provider_responses = [
                {
                    "provider_response_id": pr.get("provider_response_id", ""),
                    "provider": pr.get("provider", "unknown"),
                    "recommendation": pr.get("recommendation", ""),
                    "artifact_path": pr.get("artifact_path", ""),
                }
                for pr in provider_responses_by_prompt_id.get(prompt_id, [])
            ]
            prompts.append(
                {
                    "prompt_packet_id": prompt_id,
                    "created_at": prompt.get("created_at", ""),
                    "artifact_path": prompt.get("artifact_path", ""),
                    "provider_responses": provider_responses,
                }
            )

        entries.append(
            {
                "run_id": run_id,
                "symbol": research.get("symbol", ""),
                "created_at": research.get("created_at", ""),
                "research_path": research.get("artifact_path", ""),
                "plans": plans,
                "prompts": prompts,
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

    return {
        "ok": True,
        "status": "research_timeline",
        "entries": entries,
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
