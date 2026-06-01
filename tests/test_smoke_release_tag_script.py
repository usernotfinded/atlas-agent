"""Tests for scripts/smoke_release_tag.sh.

These tests verify the smoke script's behavior using fake git/python commands
so no network access or real cloning is required.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest


SCRIPT_PATH = Path("scripts/smoke_release_tag.sh")


def _write_fake_command(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _make_fake_git(bin_dir: Path, expected_tag: str = "v0.5.7.dev2", expected_repo: str = "https://example.com/repo.git", readme_links: str = "") -> None:
    """Write a fake git that handles the commands the smoke script uses."""
    readme_content = readme_links if readme_links else ""
    body = textwrap.dedent(
        f'''\
        set -euo pipefail
        CMD="$1"
        if [[ "$CMD" == "config" ]]; then
            echo "{expected_repo}"
            exit 0
        fi
        if [[ "$CMD" == "clone" ]]; then
            # git clone --depth 1 --branch <tag> <repo> <dest>
            DEST="$7"
            BRANCH="$4"
            REPO="$6"
            # Log clone args to an external file if requested (outside smoke temp dir)
            if [[ -n "${{FAKE_GIT_CLONE_LOG:-}}" ]]; then
                printf '%s\\n' "$REPO" >> "$FAKE_GIT_CLONE_LOG"
            fi
            mkdir -p "$DEST"
            mkdir -p "$DEST/src/atlas_agent"
            mkdir -p "$DEST/scripts"
            mkdir -p "$DEST/docs/releases"
            mkdir -p "$DEST/docs"

            TAG_NO_V="${{BRANCH#v}}"
            printf 'version = \"%s\"\\n' "$TAG_NO_V" > "$DEST/pyproject.toml"
            printf 'import atlas_agent\\n__version__ = \"%s\"\\n' "$TAG_NO_V" > "$DEST/src/atlas_agent/__init__.py"

            cat > "$DEST/scripts/check_version_consistency.py" <<'PYEOF'
        import sys
        if len(sys.argv) > 1:
            print("Version consistency OK: " + sys.argv[1])
        else:
            print("Version consistency OK: " + "{expected_tag[1:]}")
        PYEOF
            cat > "$DEST/scripts/check_forbidden_claims.py" <<'PYEOF'
        print("Forbidden claims scan clean.")
        PYEOF
            cat > "$DEST/scripts/release_check.sh" <<'SHEOF'
        #!/usr/bin/env bash
        echo "All release checks passed."
        SHEOF
            chmod +x "$DEST/scripts/release_check.sh"
            touch "$DEST/docs/releases/{expected_tag}.md"
            touch "$DEST/docs/live-submit-safety-contract.md"
            printf '%s\\n' "{readme_content}" > "$DEST/README.md"
            exit 0
        fi
        if [[ "$CMD" == "describe" ]]; then
            echo "{expected_tag}"
            exit 0
        fi
        echo "Fake git: unhandled args: $*" >&2
        exit 1
        '''
    )
    _write_fake_command(bin_dir, "git", body)


def _make_fake_python3_11(bin_dir: Path, expected_version: str = "0.5.7.dev2", quote_style: str = '"') -> None:
    """Write a fake python3.11 that handles the commands the smoke script uses."""
    body = textwrap.dedent(
        f'''\
        set -euo pipefail
        if [[ "$1" == "-m" && "$2" == "venv" ]]; then
            VENV="$3"
            mkdir -p "$VENV/bin"
            cat > "$VENV/bin/activate" <<'ACTEOF'
        # fake activate
        ACTEOF
            cp "$0" "$VENV/bin/python"
            chmod +x "$VENV/bin/python"
            exit 0
        fi
        if [[ "$1" == "-m" && "$2" == "pip" ]]; then
            for arg in "$@"; do
                if [[ "$arg" == "check" ]]; then
                    echo "No broken requirements found."
                    exit 0
                fi
            done
            exit 0
        fi
        if [[ "$1" == "-c" ]]; then
            CODE="$2"
            if [[ "$CODE" == *"import atlas_agent"* ]]; then
                echo "{expected_version}"
                exit 0
            fi
            if [[ "$CODE" == *"sysconfig.get_path"* ]]; then
                echo "/fake/purelib"
                exit 0
            fi
            if [[ "$CODE" == *"from pathlib import Path"* && "$CODE" == *"re.search"* ]]; then
                # This is the regex parser for __version__
                # Read the file and echo the version
                # The fake file has __version__ = {quote_style}{expected_version}{quote_style}
                echo "{expected_version}"
                exit 0
            fi
        fi
        if [[ "$1" == "scripts/check_version_consistency.py" ]]; then
            echo "Version consistency OK: {expected_version}"
            exit 0
        fi
        if [[ "$1" == "scripts/check_forbidden_claims.py" ]]; then
            echo "Forbidden claims scan clean."
            exit 0
        fi
        if [[ "$1" == *_parse_version.py ]]; then
            echo "{expected_version}"
            exit 0
        fi
        echo "Fake python3.11: unhandled args: $*" >&2
        exit 1
        '''
    )
    _write_fake_command(bin_dir, "python3.11", body)
    (bin_dir / "python").symlink_to("python3.11")


def _make_fake_atlas(bin_dir: Path) -> None:
    """Write a fake atlas CLI that handles the smoke script's usage."""
    body = textwrap.dedent(
        '''\
        set -euo pipefail
        if [[ "$1" == "--help" ]]; then
            echo "Usage: atlas <command>"
            exit 0
        fi
        if [[ "$1" == "init" ]]; then
            mkdir -p "$2/.atlas"
            exit 0
        fi
        if [[ "$1" == "discipline" && "$2" == "setup" ]]; then
            exit 0
        fi
        if [[ "$1" == "config" && "$2" == "set" ]]; then
            exit 0
        fi
        if [[ "$1" == "validate" ]]; then
            exit 0
        fi
        if [[ "$1" == "run" ]]; then
            exit 0
        fi
        exit 0
        '''
    )
    _write_fake_command(bin_dir, "atlas", body)


def _setup_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["ATLAS_KEEP_RELEASE_SMOKE_DIR"] = "0"
    return env, bin_dir


class TestSmokeReleaseTagScript:
    def test_script_exists_and_is_executable(self) -> None:
        assert SCRIPT_PATH.exists(), f"{SCRIPT_PATH} does not exist"
        assert os.access(SCRIPT_PATH, os.X_OK), f"{SCRIPT_PATH} is not executable"

    def test_missing_tag_exits_nonzero_and_prints_usage(self) -> None:
        result = subprocess.run(
            [str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert result.returncode == 2
        assert "usage" in (result.stdout + result.stderr).lower()

    def test_invalid_tag_exits_nonzero(self) -> None:
        result = subprocess.run(
            [str(SCRIPT_PATH), "bad-tag"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "invalid tag format" in (result.stdout + result.stderr).lower()

    def test_static_mutation_guard_no_repo_mutations(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        forbidden = [
            "git add",
            "git commit",
            "git push",
            "git tag",
            "git reset",
            "git clean",
            "git restore",
            "git switch",
        ]
        for cmd in forbidden:
            assert cmd not in content, f"Forbidden mutation command found: {cmd!r}"

    def test_no_manual_template_copy_workaround(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "CLONE_DIR/templates" not in content
        assert "cp -r" not in content

    def test_clone_uses_git_clone_not_checkout(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "git clone" in content
        lines = content.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("git checkout"):
                pytest.fail(f"Unexpected git checkout command: {line}")

    def test_fake_clone_smoke_passes_double_quoted_version(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_git(bin_dir)
        _make_fake_python3_11(bin_dir, quote_style='"')
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Smoke complete" in combined
        assert "v0.5.7.dev2 verified successfully" in combined

    def test_fake_clone_smoke_passes_single_quoted_version(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_git(bin_dir)
        _make_fake_python3_11(bin_dir, quote_style="'")
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Smoke complete" in combined

    def test_readme_missing_release_link_fails(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_git(bin_dir, readme_links="See [release notes](docs/releases/missing.md)")
        _make_fake_python3_11(bin_dir)
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Expected failure for missing release link:\n{combined}"
        assert "missing file" in combined.lower() or "missing" in combined.lower()

    def test_readme_existing_release_link_passes(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_git(bin_dir)
        _make_fake_python3_11(bin_dir)
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "README release-note links verified" in combined

    def test_repo_argument_is_passed_to_git_clone(self, tmp_path: Path) -> None:
        # Set up a fake git where config returns a DEFAULT origin URL.
        # If the smoke script ignores --repo and falls back to config, the clone
        # would use the default URL. We prove --repo overrides by logging the
        # actual URL passed to git clone.
        repo_log = tmp_path / "git_clone_args.log"
        env, bin_dir = _setup_env(tmp_path)
        env["FAKE_GIT_CLONE_LOG"] = str(repo_log)
        _make_fake_git(bin_dir, expected_repo="https://example.com/default.git")
        _make_fake_python3_11(bin_dir)
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2", "--repo", "https://example.com/custom.git"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"

        assert repo_log.exists(), "Expected git clone log to exist"
        log_content = repo_log.read_text(encoding="utf-8")
        assert "https://example.com/custom.git" in log_content, (
            f"Expected custom repo URL in clone log, got: {log_content!r}"
        )
        assert "https://example.com/default.git" not in log_content, (
            f"Default origin URL should not appear in clone log, got: {log_content!r}"
        )

    def test_full_flag_invokes_release_check(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_git(bin_dir)
        _make_fake_python3_11(bin_dir)
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2", "--full"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Full release check" in combined
        assert "All release checks passed" in combined

    def test_without_full_flag_release_check_not_invoked(self, tmp_path: Path) -> None:
        env, bin_dir = _setup_env(tmp_path)
        _make_fake_git(bin_dir)
        _make_fake_python3_11(bin_dir)
        _make_fake_atlas(bin_dir)

        result = subprocess.run(
            [str(SCRIPT_PATH), "v0.5.7.dev2"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(Path.cwd()),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"Smoke failed:\n{combined}"
        assert "Full release check" not in combined
