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
