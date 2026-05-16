from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


INDEX_FILENAME = "memory.sqlite"


@dataclass(frozen=True)
class MemoryIndexResult:
    path: Path
    snippet: str


def rebuild_memory_index(memory_dir: Path) -> int:
    memory_dir.mkdir(parents=True, exist_ok=True)
    index_path = memory_dir / INDEX_FILENAME
    files = _memory_markdown_files(memory_dir)

    with sqlite3.connect(index_path) as conn:
        conn.execute("DROP TABLE IF EXISTS memory_fts")
        conn.execute("DROP TABLE IF EXISTS memory_files")
        conn.execute("DROP TABLE IF EXISTS memory_index_meta")
        conn.execute(
            "CREATE TABLE memory_files ("
            "path TEXT PRIMARY KEY, "
            "mtime_ns INTEGER NOT NULL, "
            "size INTEGER NOT NULL, "
            "content TEXT NOT NULL)"
        )
        fts_enabled = _create_fts_table(conn)
        for path in files:
            content = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
            rel_path = path.relative_to(memory_dir).as_posix()
            conn.execute(
                "INSERT INTO memory_files(path, mtime_ns, size, content) VALUES (?, ?, ?, ?)",
                (rel_path, stat.st_mtime_ns, stat.st_size, content),
            )
            if fts_enabled:
                conn.execute(
                    "INSERT INTO memory_fts(path, content) VALUES (?, ?)",
                    (rel_path, content),
                )
        conn.execute(
            "CREATE TABLE memory_index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO memory_index_meta(key, value) VALUES ('fts_enabled', ?)",
            ("1" if fts_enabled else "0",),
        )
    return len(files)


def search_memory_index(
    memory_dir: Path,
    query: str,
    *,
    snippet_builder,
    max_results: int | None = None,
) -> list[MemoryIndexResult] | None:
    index_path = memory_dir / INDEX_FILENAME
    if not index_path.exists() or not _index_is_current(memory_dir, index_path):
        return None

    limit = max_results or -1
    with sqlite3.connect(index_path) as conn:
        fts_enabled = _fts_enabled(conn)
        rows = []
        if fts_enabled and query:
            try:
                rows.extend(conn.execute(
                    "SELECT path, content FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                    (_fts_phrase(query), limit),
                ).fetchall())
            except sqlite3.OperationalError:
                rows = []
        rows.extend(conn.execute(
            "SELECT path, content FROM memory_files WHERE lower(content) LIKE ? ORDER BY path LIMIT ?",
            (f"%{query.lower()}%", limit),
        ).fetchall())

    results: list[MemoryIndexResult] = []
    query_lower = query.lower()
    seen_paths: set[str] = set()
    for rel_path, content in rows:
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)
        index = content.lower().find(query_lower)
        if index < 0:
            continue
        results.append(
            MemoryIndexResult(
                path=memory_dir / rel_path,
                snippet=snippet_builder(content, index, len(query)),
            )
        )
    return results


def _create_fts_table(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE memory_fts USING fts5(path UNINDEXED, content)")
        return True
    except sqlite3.OperationalError:
        return False


def _fts_enabled(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT value FROM memory_index_meta WHERE key = 'fts_enabled'"
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(row and row[0] == "1")


def _fts_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _index_is_current(memory_dir: Path, index_path: Path) -> bool:
    try:
        with sqlite3.connect(index_path) as conn:
            indexed = {
                row[0]: (int(row[1]), int(row[2]))
                for row in conn.execute("SELECT path, mtime_ns, size FROM memory_files")
            }
    except sqlite3.Error:
        return False

    current: dict[str, tuple[int, int]] = {}
    for path in _memory_markdown_files(memory_dir):
        stat = path.stat()
        current[path.relative_to(memory_dir).as_posix()] = (stat.st_mtime_ns, stat.st_size)
    return current == indexed


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
