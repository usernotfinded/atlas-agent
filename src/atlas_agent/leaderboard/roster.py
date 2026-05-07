from __future__ import annotations

import os
import sysconfig
from dataclasses import dataclass
from pathlib import Path

from atlas_agent.leaderboard.cache import read_cache, write_cache
from atlas_agent.leaderboard.model_normalizer import (
    ModelMapping,
    NormalizedModel,
    load_model_mappings,
    normalize_entry,
)
from atlas_agent.leaderboard.vals_finance_agent import (
    DEFAULT_BENCHMARK_URL,
    BenchmarkEntry,
    fallback_entries,
    fetch_and_parse,
    now_utc_iso,
)


CONFIG_DIR = Path("configs")
ROSTER_FILE = "model_roster.yaml"
SOURCES_FILE = "model_sources.yaml"
ROLE_NAMES = (
    "Lead Financial Analyst",
    "Fundamental Analyst",
    "Market Research Analyst",
    "Technical Analyst",
    "Risk Challenger",
    "Execution Planner",
    "Final Arbiter",
)


@dataclass(frozen=True)
class SelectedModel:
    rank: int
    model_name: str
    provider: str | None
    model_id: str | None
    score: float | None
    configured: bool
    enabled: bool
    reason: str
    role: str | None = None


@dataclass(frozen=True)
class UpdateResult:
    roster_path: Path
    cache_path: Path
    source: str
    entries: tuple[BenchmarkEntry, ...]
    message: str


@dataclass(frozen=True)
class RoleAssignmentResult:
    roles: tuple[SelectedModel, ...]
    fallback_used: bool
    message: str


def update_model_roster(source: str = "vals-finance-agent") -> UpdateResult:
    if source != "vals-finance-agent":
        raise ValueError(f"unknown model roster source: {source}")
    source_config = load_source_config()
    url = source_config.get("url", DEFAULT_BENCHMARK_URL)
    top_n = int(source_config.get("top_n", "7"))
    message = "updated from live benchmark"
    source_label = "live"
    try:
        entries = fetch_and_parse(url)
        if not entries:
            raise ValueError("no entries parsed from benchmark page")
        entries = _top_up_entries(entries, top_n)
    except Exception as exc:
        cache = read_cache()
        if cache and cache.get("models"):
            entries = [_entry_from_cache(item) for item in cache["models"]]
            message = f"live update failed; used cache ({exc.__class__.__name__})"
            source_label = "cache"
        else:
            entries = fallback_entries()
            message = f"live update failed; used built-in fallback ({exc.__class__.__name__})"
            source_label = "built-in fallback"
    entries = tuple(sorted(entries, key=lambda item: item.rank)[:top_n])
    roster_path = write_roster(entries)
    cache_path = write_cache(
        {
            "source": source,
            "generated_at": now_utc_iso(),
            "models": [entry.__dict__ for entry in entries],
        }
    )
    return UpdateResult(
        roster_path=roster_path,
        cache_path=cache_path,
        source=source_label,
        entries=entries,
        message=message,
    )


def list_roster() -> tuple[NormalizedModel, ...]:
    return _normalized_roster()


def select_top_models(top: int = 7) -> tuple[SelectedModel, ...]:
    normalized = _normalized_roster()
    selected: list[SelectedModel] = []
    for item in normalized[:top]:
        selected.append(_selected_from_normalized(item))
    while len(selected) < top:
        selected.append(
            SelectedModel(
                rank=len(selected) + 1,
                model_name="unassigned",
                provider=None,
                model_id=None,
                score=None,
                configured=False,
                enabled=False,
                reason="no roster entry available",
            )
        )
    return tuple(selected)


def assign_committee_roles(top: int = 7) -> RoleAssignmentResult:
    selected = select_top_models(top)
    enabled = [item for item in selected if item.enabled]
    roles: list[SelectedModel] = []
    fallback_used = len(enabled) < len(ROLE_NAMES)
    for index, role in enumerate(ROLE_NAMES):
        if enabled:
            base = enabled[index % len(enabled)]
        else:
            base = selected[index % len(selected)]
        roles.append(
            SelectedModel(
                rank=base.rank,
                model_name=base.model_name,
                provider=base.provider,
                model_id=base.model_id,
                score=base.score,
                configured=base.configured,
                enabled=base.enabled,
                reason=base.reason,
                role=role,
            )
        )
    if fallback_used:
        message = (
            f"models auto: {len(enabled)} usable models; "
            "fallback role assignment used"
        )
    else:
        message = "models auto: 7 usable models assigned"
    return RoleAssignmentResult(tuple(roles), fallback_used, message)


def doctor_roster() -> tuple[str, ...]:
    roster_path = resolve_config_path(ROSTER_FILE, required=False)
    sources_path = resolve_config_path(SOURCES_FILE, required=False)
    cache = read_cache()
    lines = [
        f"roster: {'found' if roster_path else 'missing'}",
        f"cache: {'found' if cache else 'missing'}",
        f"model mappings: {'found' if sources_path else 'missing'}",
    ]
    selected = select_top_models(7)
    for item in selected:
        env_status = "set" if item.configured else "missing"
        lines.append(
            f"{item.rank}. {item.model_name}: provider={item.provider or 'none'} "
            f"env={item.env_label if hasattr(item, 'env_label') else env_status} "
            f"enabled={'yes' if item.enabled else 'no'} reason={item.reason}"
        )
    return tuple(lines)


def format_models_table(models: tuple[NormalizedModel, ...]) -> str:
    if not models:
        return "No model roster found."
    lines = ["rank | model | provider | score | configured | enabled"]
    for item in models:
        score = "n/a" if item.score is None else f"{item.score:.2f}%"
        lines.append(
            f"{item.rank} | {item.model_name} | {item.provider or 'none'} | "
            f"{score} | {'yes' if item.configured else 'no'} | "
            f"{'yes' if item.enabled else 'no'}"
        )
    return "\n".join(lines)


def format_selection(models: tuple[SelectedModel, ...]) -> str:
    lines = ["rank | model | provider | enabled | reason"]
    for item in models:
        lines.append(
            f"{item.rank} | {item.model_name} | {item.provider or 'none'} | "
            f"{'yes' if item.enabled else 'no'} | {item.reason}"
        )
    return "\n".join(lines)


def write_roster(entries: tuple[BenchmarkEntry, ...] | list[BenchmarkEntry]) -> Path:
    path = Path.cwd() / CONFIG_DIR / ROSTER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    updated = entries[0].benchmark_updated if entries else None
    lines = [
        "source: vals-finance-agent",
        f'benchmark_name: "{entries[0].benchmark_name if entries else "Vals AI Finance Agent"}"',
        f'benchmark_url: "{entries[0].benchmark_url if entries else DEFAULT_BENCHMARK_URL}"',
        f'benchmark_updated: "{updated or ""}"',
        f'generated_at: "{now_utc_iso()}"',
        "models:",
    ]
    for entry in entries:
        score = "" if entry.score is None else f"{entry.score:.2f}"
        lines.extend(
            [
                f"  - rank: {entry.rank}",
                f'    model_name: "{_escape(entry.model_name)}"',
                f'    provider: "{_escape(entry.provider)}"',
                f"    score: {score}",
                f'    benchmark_name: "{_escape(entry.benchmark_name)}"',
                f'    benchmark_url: "{_escape(entry.benchmark_url)}"',
                f'    benchmark_updated: "{entry.benchmark_updated or ""}"',
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_roster(path: str | Path | None = None) -> tuple[BenchmarkEntry, ...]:
    roster_path = Path(path) if path else resolve_config_path(ROSTER_FILE, required=False)
    if roster_path is None or not roster_path.exists():
        return tuple(fallback_entries())
    return tuple(_parse_roster_yaml(roster_path.read_text(encoding="utf-8")))


def load_source_config() -> dict[str, str]:
    path = resolve_config_path(SOURCES_FILE, required=False)
    if path is None:
        return {"url": DEFAULT_BENCHMARK_URL, "top_n": "7", "fallback_cache": "true"}
    values: dict[str, str] = {}
    in_source = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "vals_finance_agent:":
            in_source = True
            continue
        if in_source and line and not line.startswith("  "):
            break
        if in_source and ":" in stripped:
            key, value = stripped.split(":", 1)
            values[key.strip()] = _parse_scalar(value)
    return values or {"url": DEFAULT_BENCHMARK_URL, "top_n": "7", "fallback_cache": "true"}


def resolve_config_path(name: str, *, required: bool = True) -> Path | None:
    candidates = (
        Path.cwd() / CONFIG_DIR / name,
        Path(__file__).resolve().parents[3] / CONFIG_DIR / name,
        Path(sysconfig.get_path("data")) / "share" / "atlas-agent" / "configs" / name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if required:
        raise FileNotFoundError(f"configuration file not found: {name}")
    return None


def _normalized_roster() -> tuple[NormalizedModel, ...]:
    roster = load_roster()
    sources_path = resolve_config_path(SOURCES_FILE, required=False)
    mappings: dict[str, ModelMapping] = (
        load_model_mappings(sources_path) if sources_path else {}
    )
    return tuple(normalize_entry(entry, mappings) for entry in roster)


def _top_up_entries(entries: list[BenchmarkEntry], top_n: int) -> list[BenchmarkEntry]:
    seen = {entry.model_name.casefold() for entry in entries}
    topped = list(entries)
    for fallback in fallback_entries():
        if len(topped) >= top_n:
            break
        if fallback.model_name.casefold() not in seen:
            topped.append(
                BenchmarkEntry(
                    rank=len(topped) + 1,
                    model_name=fallback.model_name,
                    provider=fallback.provider,
                    score=fallback.score,
                    benchmark_updated=fallback.benchmark_updated,
                )
            )
    return topped


def _selected_from_normalized(item: NormalizedModel) -> SelectedModel:
    return SelectedModel(
        rank=item.rank,
        model_name=item.model_name,
        provider=item.provider,
        model_id=item.model_id,
        score=item.score,
        configured=item.configured,
        enabled=item.enabled,
        reason=item.reason,
    )


def _entry_from_cache(item: dict) -> BenchmarkEntry:
    return BenchmarkEntry(
        rank=int(item["rank"]),
        model_name=str(item["model_name"]),
        provider=str(item.get("provider", "unknown")),
        score=float(item["score"]) if item.get("score") not in {None, ""} else None,
        benchmark_name=str(item.get("benchmark_name", "Vals AI Finance Agent")),
        benchmark_url=str(item.get("benchmark_url", DEFAULT_BENCHMARK_URL)),
        benchmark_updated=item.get("benchmark_updated"),
    )


def _parse_roster_yaml(text: str) -> list[BenchmarkEntry]:
    entries: list[BenchmarkEntry] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current:
                entries.append(_entry_from_roster_dict(current))
            current = {}
            key_value = stripped[2:]
            if ":" in key_value:
                key, value = key_value.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
            continue
        if current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value)
    if current:
        entries.append(_entry_from_roster_dict(current))
    return entries


def _entry_from_roster_dict(values: dict[str, str]) -> BenchmarkEntry:
    score_raw = values.get("score", "")
    return BenchmarkEntry(
        rank=int(values.get("rank", "0")),
        model_name=values.get("model_name", ""),
        provider=values.get("provider", "unknown"),
        score=float(score_raw) if score_raw else None,
        benchmark_name=values.get("benchmark_name", "Vals AI Finance Agent"),
        benchmark_url=values.get("benchmark_url", DEFAULT_BENCHMARK_URL),
        benchmark_updated=values.get("benchmark_updated") or None,
    )


def _escape(value: str) -> str:
    return value.replace('"', '\\"')


def _parse_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def update_readme_roster() -> None:
    readme_path = Path("README.md")
    if not readme_path.exists():
        raise ValueError("README.md not found in current directory.")
        
    content = readme_path.read_text(encoding="utf-8")
    start_marker = "<!-- ATLAS_MODEL_ROSTER_START -->"
    end_marker = "<!-- ATLAS_MODEL_ROSTER_END -->"
    
    if start_marker not in content or end_marker not in content:
        raise ValueError(f"Missing {start_marker} or {end_marker} in README.md.")
        
    models = list_roster()[:7]
    
    table_lines = [
        "| Rank | Model | Score |",
        "|---|---|---|"
    ]
    
    for model in models:
        rank = str(model.rank)
        model_name = model.model_name
        score_str = f"{model.score:.2f}%" if model.score is not None else "N/A"
        
        table_lines.append(f"| {rank} | {model_name} | {score_str} |")
        
    table_content = "\n".join(table_lines)
    
    start_idx = content.find(start_marker) + len(start_marker)
    end_idx = content.find(end_marker)
    
    new_content = content[:start_idx] + "\n\n" + table_content + "\n\n" + content[end_idx:]
    readme_path.write_text(new_content, encoding="utf-8")
