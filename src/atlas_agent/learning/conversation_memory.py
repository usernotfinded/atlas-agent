from __future__ import annotations

import datetime
import re
from pathlib import Path

from atlas_agent.learning.memory_index import rebuild_memory_index, search_memory_index


SECRET_VALUE_RE = re.compile(
    r"(?P<name>[A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET_KEY|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"\s*=\s*"
    r"(?P<value>[^\s]+)",
    re.IGNORECASE,
)

MAX_SNIPPET_CHARS = 220


def ingest_conversation(memory_dir: Path, conversation_file: Path) -> Path:
    target_dir = memory_dir / "conversations"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    target_path = target_dir / f"{timestamp}-{conversation_file.name}"

    content = conversation_file.read_text(encoding="utf-8")
    target_path.write_text(content, encoding="utf-8")

    _update_index(memory_dir, target_path)
    return target_path


def search_memory(memory_dir: Path, query: str) -> list[tuple[Path, str]]:
    if not memory_dir.exists():
        return []

    indexed = search_memory_index(
        memory_dir,
        query,
        snippet_builder=_build_snippet,
    )
    if indexed is not None:
        return [(item.path, item.snippet) for item in indexed]

    results: list[tuple[Path, str]] = []
    query_lower = query.lower()
    for path in _memory_markdown_files(memory_dir):
        content = path.read_text(encoding="utf-8", errors="replace")
        if query_lower in content.lower():
            idx = content.lower().find(query_lower)
            results.append((path, _build_snippet(content, idx, len(query))))

    return results


def rebuild_search_index(memory_dir: Path) -> int:
    return rebuild_memory_index(memory_dir)


def _update_index(memory_dir: Path, conversation_path: Path) -> None:
    index_path = memory_dir / "conversation_index.md"
    entry = f"- {conversation_path.name} (Added: {datetime.date.today().isoformat()})\n"

    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        if entry not in content:
            index_path.write_text(content + entry, encoding="utf-8")
    else:
        index_path.write_text(f"# Conversation Index\n\n{entry}", encoding="utf-8")


def _memory_markdown_files(memory_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(memory_dir.glob("*.md")):
        if path.is_file():
            files.append(path)
    conversations_dir = memory_dir / "conversations"
    if conversations_dir.exists():
        for path in sorted(conversations_dir.rglob("*.md")):
            if path.is_file() and path not in files:
                files.append(path)
    return files


def _redact_snippet(text: str) -> str:
    return SECRET_VALUE_RE.sub(r"\g<name>=[REDACTED]", text)


def _build_snippet(content: str, index: int, query_length: int) -> str:
    start = max(0, index - 80)
    end = min(len(content), index + MAX_SNIPPET_CHARS)
    snippet = _redact_snippet(content[start:end])
    return " ".join(snippet.split())
