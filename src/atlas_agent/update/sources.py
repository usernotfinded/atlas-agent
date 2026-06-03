from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


try:
    from packaging.version import InvalidVersion, Version
except Exception:  # pragma: no cover - optional dependency path
    Version = None  # type: ignore[assignment]
    InvalidVersion = Exception  # type: ignore[assignment]


class UpdateSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class AvailableUpdate:
    latest_version: str
    source: str
    notes: str | None = None
    url: str | None = None


class UpdateSource(Protocol):
    name: str

    def check(self, current_version: str) -> AvailableUpdate | None:
        ...


JsonFetcher = Callable[[str], Any]


@dataclass
class GitHubReleaseSource:
    repo: str
    fetch_json: JsonFetcher | None = None
    name: str = "github"

    def check(self, current_version: str) -> AvailableUpdate | None:
        fetch_json = self.fetch_json or _default_fetch_json
        release_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        try:
            release_data = fetch_json(release_url)
        except UpdateSourceError:
            raise
        except Exception as exc:
            raise UpdateSourceError(f"GitHub latest release request failed: {exc}") from exc

        if not isinstance(release_data, dict):
            release_data = {}
        raw_version = str(release_data.get("tag_name") or "").strip()
        notes = _trim_note(str(release_data.get("body") or "").strip())
        page_url = str(release_data.get("html_url") or "").strip() or None

        if not raw_version:
            tags_url = f"https://api.github.com/repos/{self.repo}/tags?per_page=10"
            try:
                tags = fetch_json(tags_url)
            except Exception as exc:
                raise UpdateSourceError(f"GitHub tags request failed: {exc}") from exc
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, dict):
                        tv = str(t.get("name") or "").strip()
                        if tv and is_public_stable(tv):
                            raw_version = tv
                            break

        latest = strip_version_prefix(raw_version)
        if not latest or not is_public_stable(latest):
            return None
        if not is_version_newer(latest, current_version):
            return None
        return AvailableUpdate(
            latest_version=latest,
            source=f"github:{self.repo}",
            notes=notes,
            url=page_url,
        )


@dataclass
class PyPIReleaseSource:
    package_name: str
    fetch_json: JsonFetcher | None = None
    name: str = "pypi"

    def check(self, current_version: str) -> AvailableUpdate | None:
        fetch_json = self.fetch_json or _default_fetch_json
        url = f"https://pypi.org/pypi/{self.package_name}/json"
        try:
            payload = fetch_json(url)
        except UpdateSourceError:
            raise
        except Exception as exc:
            raise UpdateSourceError(f"PyPI request failed: {exc}") from exc
        info = payload.get("info") if isinstance(payload, dict) else None
        if not isinstance(info, dict):
            return None
        latest = strip_version_prefix(str(info.get("version") or "").strip())
        if not latest:
            return None
        if not is_version_newer(latest, current_version):
            return None
        notes = _trim_note(str(info.get("summary") or "").strip())
        return AvailableUpdate(
            latest_version=latest,
            source=f"pypi:{self.package_name}",
            notes=notes,
            url=f"https://pypi.org/project/{self.package_name}/",
        )


def discover_github_repo(repo_root: str | Path) -> str | None:
    root = Path(repo_root)
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    remote = result.stdout.strip()
    if not remote:
        return None
    return _parse_github_slug(remote)



def is_public_stable(value: str) -> bool:
    clean = strip_version_prefix(value)
    if Version is not None:
        try:
            v = Version(clean)
            return not (v.is_prerelease or v.is_devrelease)
        except InvalidVersion:
            pass
    lower = clean.lower()
    return "dev" not in lower and "rc" not in lower and "a" not in lower and "b" not in lower


def is_version_newer(candidate: str, current: str) -> bool:
    clean_candidate = strip_version_prefix(candidate)
    clean_current = strip_version_prefix(current)
    if not clean_candidate:
        return False
    if Version is not None:
        try:
            return Version(clean_candidate) > Version(clean_current)
        except InvalidVersion:
            pass
    return _fallback_compare(clean_candidate, clean_current) > 0


def strip_version_prefix(value: str) -> str:
    raw = value.strip()
    if raw.lower().startswith("v"):
        return raw[1:]
    return raw


def _default_fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "atlas-agent-update-manager",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise UpdateSourceError(str(exc.reason) or str(exc)) from exc
    except Exception as exc:
        raise UpdateSourceError(str(exc)) from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise UpdateSourceError(f"invalid JSON payload from {url}") from exc
    return payload


def _parse_github_slug(remote: str) -> str | None:
    value = remote.strip()
    ssh_match = re.match(r"^git@github\.com:(?P<slug>[^ ]+?)(?:\.git)?$", value)
    if ssh_match:
        return ssh_match.group("slug")
    https_match = re.match(r"^https://github\.com/(?P<slug>[^ ]+?)(?:\.git)?/?$", value)
    if https_match:
        return https_match.group("slug")
    ssh_url_match = re.match(r"^ssh://git@github\.com/(?P<slug>[^ ]+?)(?:\.git)?/?$", value)
    if ssh_url_match:
        return ssh_url_match.group("slug")
    return None


def _fallback_compare(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    for idx in range(max_len):
        left_part = left_parts[idx] if idx < len(left_parts) else None
        right_part = right_parts[idx] if idx < len(right_parts) else None
        if left_part == right_part:
            continue
        if left_part is None:
            if isinstance(right_part, str):
                return 1
            return -1
        if right_part is None:
            if isinstance(left_part, str):
                return -1
            return 1
        if isinstance(left_part, int) and isinstance(right_part, int):
            return 1 if left_part > right_part else -1
        if isinstance(left_part, int) and isinstance(right_part, str):
            return 1
        if isinstance(left_part, str) and isinstance(right_part, int):
            return -1
        return 1 if str(left_part) > str(right_part) else -1
    return 0


def _version_parts(value: str) -> list[int | str]:
    tokens = re.findall(r"\d+|[A-Za-z]+", value)
    parts: list[int | str] = []
    for token in tokens:
        if token.isdigit():
            parts.append(int(token))
        else:
            parts.append(token.lower())
    return parts


def _trim_note(note: str) -> str | None:
    if not note:
        return None
    return note[:400]
