from __future__ import annotations

from pathlib import Path


def test_gitignore_covers_runtime_artifacts() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    for pattern in (
        "events/*.jsonl",
        "pending_orders/*.json",
        "audit/*.jsonl",
        "reports/**/*.md",
        "reports/*.json",
        "reports/*.csv",
        "demo-workspace/",
        ".atlas/cache/",
        "*.egg-info/",
        ".env",
    ):
        assert pattern in gitignore
