from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime


DEFAULT_BENCHMARK_URL = "https://www.vals.ai/benchmarks/finance_agent"
BENCHMARK_NAME = "Vals AI Finance Agent"


@dataclass(frozen=True)
class BenchmarkEntry:
    rank: int
    model_name: str
    provider: str
    score: float | None
    benchmark_name: str = BENCHMARK_NAME
    benchmark_url: str = DEFAULT_BENCHMARK_URL
    benchmark_updated: str | None = None


class ValsFinanceAgentError(RuntimeError):
    pass


def fetch_benchmark_html(url: str = DEFAULT_BENCHMARK_URL, *, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "atlas-agent-model-roster/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_benchmark_html(
    raw_html: str,
    *,
    benchmark_url: str = DEFAULT_BENCHMARK_URL,
) -> list[BenchmarkEntry]:
    updated = _extract_updated_date(raw_html)
    entries = _parse_table_entries(raw_html, benchmark_url, updated)
    if not entries:
        entries = _parse_key_takeaway_entries(raw_html, benchmark_url, updated)
    return _dedupe(entries)


def fetch_and_parse(url: str = DEFAULT_BENCHMARK_URL) -> list[BenchmarkEntry]:
    return parse_benchmark_html(fetch_benchmark_html(url), benchmark_url=url)


def fallback_entries() -> list[BenchmarkEntry]:
    # First five entries are from the Vals Finance Agent v1.1 key takeaways
    # observed on 2026-05-07. Remaining entries are cached placeholders because
    # the public page does not expose every leaderboard row consistently.
    updated = "2026-05-04"
    names = [
        ("Claude Opus 4.7", "anthropic", 64.37),
        ("Claude Sonnet 4.6", "anthropic", 63.33),
        ("Muse Spark", "minimax", 60.59),
        ("DeepSeek V4", "deepseek", 60.39),
        ("Claude Opus 4.6 (Thinking)", "anthropic", 60.05),
        ("GPT 5.5", "openai", None),
        ("Gemini 3.1 Pro Preview (02/26)", "google", None),
    ]
    return [
        BenchmarkEntry(
            rank=index,
            model_name=name,
            provider=provider,
            score=score,
            benchmark_updated=updated,
        )
        for index, (name, provider, score) in enumerate(names, start=1)
    ]


def _extract_updated_date(raw_html: str) -> str | None:
    text = _visible_text(raw_html)
    match = re.search(r"Updated:\s*(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if not match:
        return None
    month, day, year = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _parse_table_entries(
    raw_html: str,
    benchmark_url: str,
    updated: str | None,
) -> list[BenchmarkEntry]:
    entries: list[BenchmarkEntry] = []
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", raw_html, flags=re.I | re.S)
    headers: list[str] = []
    for row in rows:
        cells = [
            _clean_cell(cell)
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
        ]
        if not cells:
            continue
        if re.search(r"<th\b", row, flags=re.I):
            headers = [_normalize_header(cell) for cell in cells]
            continue
        entry = _entry_from_cells(cells, headers, benchmark_url, updated)
        if entry is not None:
            entries.append(entry)
    return entries


def _entry_from_cells(
    cells: list[str],
    headers: list[str],
    benchmark_url: str,
    updated: str | None,
) -> BenchmarkEntry | None:
    rank_index = _index(headers, {"rank", "#"})
    model_index = _index(headers, {"model", "model_name", "name"})
    provider_index = _index(headers, {"provider", "vendor", "company"})
    score_index = _index(headers, {"score", "accuracy"})
    if rank_index is None:
        rank_index = 0
    if model_index is None:
        model_index = 1 if len(cells) > 1 else None
    if model_index is None or rank_index >= len(cells) or model_index >= len(cells):
        return None
    rank_match = re.search(r"\d+", cells[rank_index])
    if not rank_match:
        return None
    model = cells[model_index].strip()
    if not model:
        return None
    provider = (
        cells[provider_index].strip().lower()
        if provider_index is not None and provider_index < len(cells)
        else infer_provider(model)
    )
    score = _parse_score(cells[score_index]) if score_index is not None and score_index < len(cells) else None
    return BenchmarkEntry(
        rank=int(rank_match.group(0)),
        model_name=model,
        provider=provider or infer_provider(model),
        score=score,
        benchmark_url=benchmark_url,
        benchmark_updated=updated,
    )


def _parse_key_takeaway_entries(
    raw_html: str,
    benchmark_url: str,
    updated: str | None,
) -> list[BenchmarkEntry]:
    text = _visible_text(raw_html)
    pairs: list[tuple[str, float]] = []
    first = re.search(
        r"(?P<model>[A-Z][A-Za-z0-9 .()/+-]+?)\s+is the current top performer"
        r".*?scoring\s+(?P<score>\d+(?:\.\d+)?)%",
        text,
    )
    if not first:
        return []
    pairs.append((first.group("model").strip(), float(first.group("score"))))
    tail = text[first.end() : first.end() + 500]
    for match in re.finditer(
        r"(?:[,.]|\band\b)\s*(?P<model>[A-Z][A-Za-z0-9 .()/+-]+?)"
        r"(?:\s+follows)?\s+with\s+(?P<score>\d+(?:\.\d+)?)%",
        tail,
    ):
        pairs.append((match.group("model").strip(), float(match.group("score"))))
    return [
        BenchmarkEntry(
            rank=index,
            model_name=name,
            provider=infer_provider(name),
            score=score,
            benchmark_url=benchmark_url,
            benchmark_updated=updated,
        )
        for index, (name, score) in enumerate(pairs, start=1)
    ]


def infer_provider(model_name: str) -> str:
    lower = model_name.lower()
    if "claude" in lower:
        return "anthropic"
    if "deepseek" in lower:
        return "deepseek"
    if lower.startswith("gpt") or lower.startswith("o3") or "openai" in lower:
        return "openai"
    if "gemini" in lower:
        return "google"
    if "kimi" in lower:
        return "moonshot"
    if "grok" in lower:
        return "xai"
    if "muse" in lower:
        return "minimax"
    return "unknown"


def _visible_text(raw_html: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", raw_html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _clean_cell(cell: str) -> str:
    return _visible_text(cell)


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _index(headers: list[str], names: set[str]) -> int | None:
    for index, header in enumerate(headers):
        if header in names:
            return index
    return None


def _parse_score(value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def _dedupe(entries: list[BenchmarkEntry]) -> list[BenchmarkEntry]:
    seen: set[str] = set()
    unique: list[BenchmarkEntry] = []
    for entry in sorted(entries, key=lambda item: item.rank):
        key = entry.model_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


def now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
