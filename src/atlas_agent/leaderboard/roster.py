from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.leaderboard.vals_finance_agent import (
    DEFAULT_BENCHMARK_URL,
    BenchmarkEntry,
    fallback_entries,
    fetch_and_parse,
)


README_START_MARKER = "<!-- ATLAS_MODEL_ROSTER_START -->"
README_END_MARKER = "<!-- ATLAS_MODEL_ROSTER_END -->"
ROSTER_SOURCE_VALS_FINANCE_AGENT = "vals-finance-agent"
SUPPORTED_ROSTER_SOURCES = {ROSTER_SOURCE_VALS_FINANCE_AGENT}
MAX_RECOMMENDED_MODELS = 7


def roster_config_path(root: Path | None = None) -> Path:
    base = root or Path.cwd()
    return base / "configs" / "model_roster.yaml"


def roster_cache_path() -> Path:
    return Path.home() / ".atlas" / "cache" / "vals_finance_agent_roster.json"


def list_roster(root: Path | None = None) -> tuple[BenchmarkEntry, ...]:
    config_path = roster_config_path(root)
    if config_path.exists():
        try:
            document = _load_roster_document(config_path)
            entries = _entries_from_document(document)
            if entries:
                return tuple(entries)
        except Exception:
            pass
    return tuple(fallback_entries())


def update_roster(
    *,
    source: str = ROSTER_SOURCE_VALS_FINANCE_AGENT,
    root: Path | None = None,
) -> tuple[BenchmarkEntry, ...]:
    normalized_source = source.strip().lower()
    if normalized_source not in SUPPORTED_ROSTER_SOURCES:
        raise ValueError(f"unsupported model roster source: {source}")

    data_origin = "fallback"
    entries: list[BenchmarkEntry] = []
    benchmark_url = DEFAULT_BENCHMARK_URL
    try:
        fetched = fetch_and_parse(DEFAULT_BENCHMARK_URL)
        if fetched:
            entries = fetched
            data_origin = "live"
            _write_cache(_document_from_entries(entries, source=normalized_source, data_origin=data_origin))
    except Exception:
        entries = []

    if not entries:
        cached = _load_cache_document()
        if cached is not None:
            cached_entries = _entries_from_document(cached)
            if cached_entries:
                entries = cached_entries
                data_origin = "cache"

    if not entries:
        entries = fallback_entries()
        data_origin = "fallback"

    model_entries = sorted(entries, key=lambda item: item.rank)[:MAX_RECOMMENDED_MODELS]
    config_path = roster_config_path(root)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _document_text(
            _document_from_entries(
                model_entries,
                source=normalized_source,
                data_origin=data_origin,
                benchmark_url=benchmark_url,
            )
        ),
        encoding="utf-8",
    )
    return tuple(model_entries)


def update_readme_roster(root: Path | None = None) -> None:
    base = root or Path.cwd()
    readme_path = base / "README.md"
    if not readme_path.exists():
        raise ValueError("README.md not found in current directory.")

    content = readme_path.read_text(encoding="utf-8")
    if README_START_MARKER not in content or README_END_MARKER not in content:
        raise ValueError(f"Missing {README_START_MARKER} or {README_END_MARKER} in README.md.")

    models = list_roster(base)[:MAX_RECOMMENDED_MODELS]
    table_lines = [
        "| Rank | Model | Score |",
        "|---|---|---|",
    ]
    for model in models:
        score = f"{model.score:.2f}%" if isinstance(model.score, float) else "N/A"
        table_lines.append(f"| {model.rank} | {model.model_name} | {score} |")
    table_content = "\n".join(table_lines)

    start_idx = content.index(README_START_MARKER) + len(README_START_MARKER)
    end_idx = content.index(README_END_MARKER)
    new_content = (
        content[:start_idx]
        + "\n\n"
        + table_content
        + "\n\n"
        + content[end_idx:]
    )
    readme_path.write_text(new_content, encoding="utf-8")


def doctor_roster(root: Path | None = None) -> dict[str, Any]:
    base = root or Path.cwd()
    config_path = roster_config_path(base)
    readme_path = base / "README.md"
    issues: list[str] = []
    source: str | None = None
    model_count = 0

    if not config_path.exists():
        issues.append(f"missing roster config: {config_path}")
    else:
        try:
            document = _load_roster_document(config_path)
            source = str(document.get("source") or "")
            model_count = len(document.get("models", []))
            if source not in SUPPORTED_ROSTER_SOURCES:
                issues.append(f"unsupported source in roster config: {source or 'missing'}")
            if not bool(document.get("reference_only")):
                issues.append("reference_only must be true in roster config")
            if bool(document.get("runtime_orchestration")):
                issues.append("runtime_orchestration must stay false")
            if model_count == 0:
                issues.append("roster config has zero models")
        except Exception as exc:
            issues.append(f"failed to parse roster config: {exc}")

    if not readme_path.exists():
        issues.append(f"missing README: {readme_path}")
    else:
        readme_text = readme_path.read_text(encoding="utf-8")
        if README_START_MARKER not in readme_text or README_END_MARKER not in readme_text:
            issues.append("README model roster markers are missing")

    return {
        "ok": not issues,
        "path": str(config_path),
        "source": source,
        "model_count": model_count,
        "issues": issues,
    }


def _document_from_entries(
    entries: list[BenchmarkEntry],
    *,
    source: str,
    data_origin: str,
    benchmark_url: str = DEFAULT_BENCHMARK_URL,
) -> dict[str, Any]:
    benchmark_updated = next(
        (
            entry.benchmark_updated
            for entry in entries
            if entry.benchmark_updated
        ),
        None,
    )
    benchmark_name = next(
        (
            entry.benchmark_name
            for entry in entries
            if entry.benchmark_name
        ),
        "Vals AI Finance Agent",
    )
    return {
        "source": source,
        "data_origin": data_origin,
        "reference_only": True,
        "runtime_orchestration": False,
        "guidance": (
            "The model roster is guidance for choosing models to connect. "
            "It updates the recommended-model table in this README. "
            "It is not mandatory runtime orchestration and does not guarantee trading performance."
        ),
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "benchmark": {
            "name": benchmark_name,
            "url": benchmark_url,
            "updated": benchmark_updated,
        },
        "models": [
            {
                "rank": entry.rank,
                "model_name": entry.model_name,
                "provider": entry.provider,
                "score": entry.score,
                "benchmark_name": entry.benchmark_name,
                "benchmark_url": entry.benchmark_url,
                "benchmark_updated": entry.benchmark_updated,
            }
            for entry in sorted(entries, key=lambda item: item.rank)[:MAX_RECOMMENDED_MODELS]
        ],
    }


def _document_text(document: dict[str, Any]) -> str:
    # JSON is valid YAML 1.2, so this keeps the file machine-safe without adding
    # an external YAML dependency.
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _load_roster_document(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("roster config must be a JSON/YAML object")
    return parsed


def _entries_from_document(document: dict[str, Any]) -> list[BenchmarkEntry]:
    entries: list[BenchmarkEntry] = []
    rows = document.get("models")
    if not isinstance(rows, list):
        return entries
    benchmark = document.get("benchmark", {})
    benchmark_name = (
        benchmark.get("name")
        if isinstance(benchmark, dict)
        else None
    ) or "Vals AI Finance Agent"
    benchmark_url = (
        benchmark.get("url")
        if isinstance(benchmark, dict)
        else None
    ) or DEFAULT_BENCHMARK_URL
    benchmark_updated = (
        benchmark.get("updated")
        if isinstance(benchmark, dict)
        else None
    )

    for row in rows:
        if not isinstance(row, dict):
            continue
        rank = row.get("rank")
        model_name = row.get("model_name")
        provider = row.get("provider")
        if not isinstance(rank, int):
            continue
        if not isinstance(model_name, str) or not model_name:
            continue
        if not isinstance(provider, str) or not provider:
            continue
        score = row.get("score")
        normalized_score = float(score) if isinstance(score, (int, float)) else None
        entries.append(
            BenchmarkEntry(
                rank=rank,
                model_name=model_name,
                provider=provider,
                score=normalized_score,
                benchmark_name=row.get("benchmark_name") or benchmark_name,
                benchmark_url=row.get("benchmark_url") or benchmark_url,
                benchmark_updated=row.get("benchmark_updated") or benchmark_updated,
            )
        )
    entries.sort(key=lambda item: item.rank)
    return entries


def _write_cache(document: dict[str, Any]) -> None:
    path = roster_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_document_text(document), encoding="utf-8")


def _load_cache_document() -> dict[str, Any] | None:
    path = roster_cache_path()
    if not path.exists():
        return None
    try:
        return _load_roster_document(path)
    except Exception:
        return None
