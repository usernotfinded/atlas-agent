from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from omni_trade_ai.safety.secrets import scan_file


class GitSyncError(RuntimeError):
    pass


SYNC_PATHS = ("memory", "reports")
SENSITIVE_FILENAMES = {".env"}
SENSITIVE_SUFFIXES = (".secret", ".key")


@dataclass(frozen=True)
class GitSync:
    repo_dir: Path = Path(".")
    allow_commit: bool = False
    allow_push: bool = False
    author_name: str = "OmniTradeAI Agent"
    author_email: str = "omni-trade-ai@example.local"

    @classmethod
    def from_env(cls, repo_dir: str | Path = ".") -> GitSync:
        return cls(
            repo_dir=Path(repo_dir),
            allow_commit=os.getenv("ALLOW_GIT_COMMIT", "false").lower() == "true",
            allow_push=os.getenv("ALLOW_GIT_PUSH", "false").lower() == "true",
            author_name=os.getenv("GIT_COMMIT_AUTHOR_NAME", "OmniTradeAI Agent"),
            author_email=os.getenv(
                "GIT_COMMIT_AUTHOR_EMAIL",
                "omni-trade-ai@example.local",
            ),
        )

    def commit(self, message: str) -> str:
        if not self.allow_commit:
            return "commit skipped: ALLOW_GIT_COMMIT is not true"
        self._preflight()
        sync_paths = self._existing_sync_paths()
        if not sync_paths:
            return "commit skipped: no sync paths"
        status = subprocess.run(
            ["git", "status", "--short", "--", *sync_paths],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if status.returncode != 0:
            return "commit skipped: not a git repository"
        if not status.stdout.strip():
            return "commit skipped: no changes"
        subprocess.run(["git", "add", "--", *sync_paths], cwd=self.repo_dir, check=True)
        result = subprocess.run(
            [
                "git",
                "-c",
                f"user.name={self.author_name}",
                "-c",
                f"user.email={self.author_email}",
                "commit",
                "-m",
                message,
            ],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return f"commit skipped: {result.stderr.strip() or result.stdout.strip()}"
        return "commit created"

    def push(self) -> str:
        if not self.allow_push:
            return "push skipped: ALLOW_GIT_PUSH is not true"
        self._preflight()
        result = subprocess.run(
            ["git", "push"],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return f"push failed: {result.stderr.strip() or result.stdout.strip()}"
        return "push complete"

    def status(self) -> str:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return "status skipped: not a git repository"
        lines = [
            _sanitize_status_line(line)
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        return "\n".join(lines) if lines else "working tree clean"

    def _preflight(self) -> None:
        if self._is_tracked(".env"):
            raise GitSyncError("refusing git sync because .env is tracked")
        findings: list[str] = []
        for directory in SYNC_PATHS:
            root = self.repo_dir / directory
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    if _is_sensitive_path(path):
                        findings.append(f"{path}: sensitive filename")
                    findings.extend(f"{path}: {item}" for item in scan_file(path))
        if findings:
            raise GitSyncError("refusing git sync; possible secrets found")

    def _existing_sync_paths(self) -> list[str]:
        return [path for path in SYNC_PATHS if (self.repo_dir / path).exists()]

    def _is_tracked(self, path: str) -> bool:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0


def _is_sensitive_path(path: Path) -> bool:
    return path.name in SENSITIVE_FILENAMES or path.name.endswith(SENSITIVE_SUFFIXES)


def _sanitize_status_line(line: str) -> str:
    path = line[3:].strip()
    if _is_sensitive_path(Path(path)):
        return f"{line[:3]}[sensitive file hidden]"
    return line
