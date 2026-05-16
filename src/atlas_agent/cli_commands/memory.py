from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from atlas_agent.cli_context import CLIContext
from atlas_agent.learning import ingest_conversation, rebuild_search_index
from atlas_agent.learning.nudges import generate_memory_nudge
from atlas_agent.memory_doctor import run_memory_doctor
from atlas_agent.output import emit_json, success_envelope


SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?P<name>[A-Z0-9_.-]*(?:API[_-]?KEY|API[_-]?SECRET|SECRET[_-]?KEY|TOKEN|PASSWORD)[A-Z0-9_.-]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s,;`\"']+)"
    r"(?P=quote)",
    re.IGNORECASE,
)
BEARER_TOKEN_RE = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
MAX_CLI_SNIPPET_CHARS = 220


def handle_memory(context: CLIContext) -> int:
    args = context.args
    config = context.config

    if args.memory_command == "ingest":
        if not args.file.exists():
            print(f"memory ingest skipped: file not found: {args.file}")
            return 0
        path = ingest_conversation(config.memory_dir, args.file)
        print(f"Conversation memory ingested: {path}")
        return 0

    if args.memory_command == "search":
        if getattr(args, "json", False):
            matches, warning = _memory_search_matches(config.memory_dir, args.query)
            return _emit_json_success(
                "atlas memory search",
                {
                    "query": args.query,
                    "matches": matches,
                    "warning": warning,
                },
            )
        return _handle_memory_search(config.memory_dir, args.query)

    if args.memory_command == "rebuild-index":
        count = rebuild_search_index(config.memory_dir)
        print(f"Memory search index rebuilt: {count} Markdown files indexed.")
        return 0

    if args.memory_command == "doctor":
        payload = _memory_doctor_payload(context)
        if getattr(args, "json", False):
            return _emit_json_success("atlas memory doctor", payload)
        _print_memory_doctor_text(payload)
        return 0

    if args.memory_command == "summarize":
        print("Memory summary is generated through agent learn/reflect cycles.")
        return 0

    if args.memory_command == "nudge":
        nudge = generate_memory_nudge(config.memory_dir)
        print(nudge or "No memory nudge available yet.")
        return 0

    return 0


def _emit_json_success(command: str, data: dict[str, Any]) -> int:
    emit_json(success_envelope(command, data))
    return 0


def _memory_search_matches(memory_dir: Path, query: str) -> tuple[list[dict[str, str]], str | None]:
    if not memory_dir.exists():
        return [], f"No memory directory found at {memory_dir}."

    files = _memory_markdown_files(memory_dir)
    if not files:
        return [], f"No Markdown memory files found under {memory_dir} or {memory_dir / 'conversations'}."

    query_lower = query.lower()
    matches: list[dict[str, str]] = []
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        index = content.lower().find(query_lower)
        if index < 0:
            continue
        snippet = _snippet(content, index, len(query))
        matches.append({"path": _display_path(path), "snippet": snippet})
    return matches, None


def _handle_memory_search(memory_dir: Path, query: str) -> int:
    matches, warning = _memory_search_matches(memory_dir, query)
    if warning:
        print(warning)
        return 0
    if not matches:
        print(f"No memory matches found for: {query}")
        return 0
    for match in matches:
        print(f"{match['path']}: {match['snippet']}")
    return 0


def _memory_markdown_files(memory_dir: Path) -> list[Path]:
    files = [path for path in sorted(memory_dir.glob("*.md")) if path.is_file()]
    conversations_dir = memory_dir / "conversations"
    if conversations_dir.exists():
        files.extend(
            path
            for path in sorted(conversations_dir.rglob("*.md"))
            if path.is_file()
        )
    return files


def _snippet(content: str, index: int, query_length: int) -> str:
    start = max(0, index - 80)
    end = min(len(content), index + max(query_length, 1) + 140)
    snippet = " ".join(content[start:end].split())
    if start > 0:
        snippet = "... " + snippet
    if end < len(content):
        snippet += " ..."
    snippet = _redact_sensitive_text(snippet)
    if len(snippet) > MAX_CLI_SNIPPET_CHARS:
        snippet = snippet[: MAX_CLI_SNIPPET_CHARS - 4].rstrip() + " ..."
    return snippet


def _redact_sensitive_text(text: str) -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('name')}{match.group('sep')}"
            f"{match.group('quote')}[REDACTED]{match.group('quote')}"
        ),
        text,
    )
    return BEARER_TOKEN_RE.sub(r"\1[REDACTED]", redacted)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _memory_doctor_payload(context: CLIContext) -> dict[str, Any]:
    config = context.config
    skills_dir = config.memory_dir.parent / "skills"
    result = run_memory_doctor(
        memory_dir=config.memory_dir,
        pending_orders_dir=config.pending_orders_dir,
        reports_dir=config.reports_dir,
        skills_dir=skills_dir,
        stale_hours=24,
    )
    return {
        "ok": result.ok,
        "checked_at": result.checked_at,
        "errors": [asdict(item) for item in result.errors],
        "warnings": [asdict(item) for item in result.warnings],
        "finding_count": len(result.findings),
    }


def _print_memory_doctor_text(payload: dict[str, Any]) -> None:
    print("Memory Doctor")
    print(f"Checked at: {payload['checked_at']}")
    if not payload["errors"] and not payload["warnings"]:
        print("No issues found.")
        return
    for error in payload["errors"]:
        print(f"[ERROR] {error['code']}: {error['message']} ({error.get('path') or 'n/a'})")
    for warning in payload["warnings"]:
        print(f"[WARN] {warning['code']}: {warning['message']} ({warning.get('path') or 'n/a'})")
