from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from atlas_agent.leaderboard.vals_finance_agent import BenchmarkEntry


SUPPORTED_PROVIDER_ADAPTERS = {
    "anthropic",
    "openai_compatible",
    "openrouter",
    "local_command",
    "null",
}


@dataclass(frozen=True)
class ModelMapping:
    provider: str
    env_key: str
    model_id: str
    notes: str = ""


@dataclass(frozen=True)
class NormalizedModel:
    rank: int
    model_name: str
    source_provider: str
    score: float | None
    benchmark_name: str
    benchmark_url: str
    benchmark_updated: str | None
    provider: str | None
    env_key: str | None
    model_id: str | None
    mapping_found: bool
    provider_supported: bool
    configured: bool
    enabled: bool
    reason: str


def normalize_entry(
    entry: BenchmarkEntry,
    mappings: dict[str, ModelMapping],
    *,
    environ: dict[str, str] | None = None,
) -> NormalizedModel:
    environ = environ if environ is not None else os.environ
    mapping = find_mapping(entry.model_name, mappings)
    if mapping is None:
        return NormalizedModel(
            rank=entry.rank,
            model_name=entry.model_name,
            source_provider=entry.provider,
            score=entry.score,
            benchmark_name=entry.benchmark_name,
            benchmark_url=entry.benchmark_url,
            benchmark_updated=entry.benchmark_updated,
            provider=None,
            env_key=None,
            model_id=None,
            mapping_found=False,
            provider_supported=False,
            configured=False,
            enabled=False,
            reason="missing model mapping",
        )
    provider_supported = mapping.provider in SUPPORTED_PROVIDER_ADAPTERS
    configured = bool(mapping.env_key and environ.get(mapping.env_key))
    reasons: list[str] = []
    if not provider_supported:
        reasons.append(f"provider adapter unavailable: {mapping.provider}")
    if not configured:
        reasons.append(f"missing env var: {mapping.env_key}")
    return NormalizedModel(
        rank=entry.rank,
        model_name=entry.model_name,
        source_provider=entry.provider,
        score=entry.score,
        benchmark_name=entry.benchmark_name,
        benchmark_url=entry.benchmark_url,
        benchmark_updated=entry.benchmark_updated,
        provider=mapping.provider,
        env_key=mapping.env_key,
        model_id=mapping.model_id,
        mapping_found=True,
        provider_supported=provider_supported,
        configured=configured,
        enabled=provider_supported and configured,
        reason="; ".join(reasons) if reasons else "available",
    )


def find_mapping(
    model_name: str,
    mappings: dict[str, ModelMapping],
) -> ModelMapping | None:
    if model_name in mappings:
        return mappings[model_name]
    normalized_name = normalize_model_name(model_name)
    for candidate, mapping in mappings.items():
        if normalize_model_name(candidate) == normalized_name:
            return mapping
    return None


def normalize_model_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_model_mappings(path: str | Path) -> dict[str, ModelMapping]:
    text = Path(path).read_text(encoding="utf-8")
    mappings: dict[str, ModelMapping] = {}
    in_mappings = False
    current_name: str | None = None
    current: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "model_mappings:":
            in_mappings = True
            continue
        if not in_mappings:
            continue
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            if current_name is not None:
                mappings[current_name] = _mapping_from_dict(current)
            current_name = _parse_key(stripped[:-1])
            current = {}
            continue
        if current_name is not None and line.startswith("    ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value)
    if current_name is not None:
        mappings[current_name] = _mapping_from_dict(current)
    return mappings


def _mapping_from_dict(values: dict[str, str]) -> ModelMapping:
    return ModelMapping(
        provider=values.get("provider", ""),
        env_key=values.get("env_key", ""),
        model_id=values.get("model_id", ""),
        notes=values.get("notes", ""),
    )


def _parse_key(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _parse_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")
