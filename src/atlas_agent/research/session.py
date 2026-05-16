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
