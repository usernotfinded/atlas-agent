from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atlas_agent.events.log import EventLogger, generate_run_id

if TYPE_CHECKING:
    from atlas_agent.learning.memory_index import MemoryIndexResult
    from atlas_agent.research.research_report import ResearchReport


RESEARCH_DIR = Path(".atlas") / "research"


class ResearchSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResearchArtifact:
    symbol: str
    mode: str
    provider: str
    summary: str
    citations: tuple[str, ...]
    memory_hits: list[dict[str, str]]
    run_id: str
    created_at: datetime
    artifact_path: str


def sanitize_symbol(symbol: str) -> str:
    """Return a filesystem-safe sanitized symbol. Blocks path traversal."""
    if not symbol:
        raise ResearchSessionError("symbol must not be empty")
    # Reject any symbols that look like paths
    if "/" in symbol or "\\" in symbol or symbol.startswith(".") or ".." in symbol:
        raise ResearchSessionError(f"symbol contains path traversal characters: {symbol}")
    # Only allow printable alphanumeric, dash, underscore, dot in the middle
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
    # Never emit absolute paths or raw memory bodies
    rel = Path(hit.path).name
    return {"file": rel, "snippet": hit.snippet[:200]}


def run_research_session(
    symbol: str,
    workspace_path: Path,
    *,
    memory_dir: Path | None = None,
    event_logger: EventLogger | None = None,
    provider: Any | None = None,
) -> ResearchArtifact:
    """Run a paper-only research session and persist a safe artifact.

    This never touches broker submit paths.
    """
    safe_symbol = sanitize_symbol(symbol)
    run_id = generate_run_id()
    created_at = datetime.now(UTC)

    # Resolve provider
    if provider is not None:
        research_provider = provider
    else:
        from atlas_agent.research import get_research_provider
        research_provider = get_research_provider()
    report: ResearchReport = research_provider.research_market(safe_symbol)

    # Optional memory search — never fails
    memory_hits: list[dict[str, str]] = []
    if memory_dir is not None and memory_dir.exists():
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
            pass

    # Build artifact
    artifact = ResearchArtifact(
        symbol=safe_symbol,
        mode="paper",
        provider=report.provider,
        summary=report.summary,
        citations=report.citations,
        memory_hits=memory_hits,
        run_id=run_id,
        created_at=created_at,
        artifact_path="",  # filled below
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
        citations=artifact.citations,
        memory_hits=artifact.memory_hits,
        run_id=artifact.run_id,
        created_at=artifact.created_at,
        artifact_path=artifact_file.relative_to(workspace_path).as_posix(),
    )

    # Log event with safe payload
    if event_logger is not None:
        payload = {
            "symbol": safe_symbol,
            "provider": report.provider,
            "memory_hits_count": len(memory_hits),
            "artifact_path": artifact.artifact_path,
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
        "symbol": artifact.symbol,
        "mode": artifact.mode,
        "provider": artifact.provider,
        "summary": artifact.summary,
        "citations": list(artifact.citations),
        "memory_hits": artifact.memory_hits,
        "run_id": artifact.run_id,
        "created_at": artifact.created_at.isoformat(),
        "artifact_path": artifact.artifact_path,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
