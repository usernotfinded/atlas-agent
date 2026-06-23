"""Tests for release-assurance failure diagnostics and redaction (CAND-011)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_release_assurance_diagnostics import check_diagnostics

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE_SCRIPT = REPO_ROOT / "scripts" / "release_assurance.py"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_release_assurance_diagnostics.py"


def _run_release_assurance(
    output_dir: Path,
    *extra_args: str,
    version: str = "v0.0.0-does-not-exist",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RELEASE_ASSURANCE_SCRIPT),
            "--version",
            version,
            "--output",
            str(output_dir),
            *extra_args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_failure_output_includes_failing_check_name(tmp_path: Path) -> None:
    result = _run_release_assurance(tmp_path)
    assert result.returncode == 1, result.stdout
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    failing = [name for name, passed in summary["checks"].items() if not passed]
    assert failing
    assert any(name in result.stderr for name in failing)


def test_failure_output_includes_release_version(tmp_path: Path) -> None:
    version = "v0.0.0-does-not-exist"
    result = _run_release_assurance(tmp_path, version=version)
    assert result.returncode == 1, result.stdout
    assert version in result.stderr


def test_failure_output_includes_output_directory(tmp_path: Path) -> None:
    result = _run_release_assurance(tmp_path)
    assert result.returncode == 1, result.stdout
    assert str(tmp_path) in result.stderr


def test_failure_output_includes_remediation_hint(tmp_path: Path) -> None:
    result = _run_release_assurance(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "remediation" in result.stderr.lower()


def test_subprocess_failure_includes_exit_code_and_sanitized_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    diagnostics_path = tmp_path / "diagnostics.json"

    def failing_run_cmd(cmd, check=True, cwd=None, env=None):
        return "", 2, "gh: GH_TOKEN=ghp_1234567890abcdefgh is not valid"

    monkeypatch.setattr("release_assurance.run_cmd", failing_run_cmd)
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_assurance.py",
            "--version",
            "v0.6.15",
            "--output",
            str(tmp_path),
            "--diagnostics-json",
            str(diagnostics_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        release_assurance.main()

    assert exc_info.value.code == 1
    assert diagnostics_path.exists()
    diag = json.loads(diagnostics_path.read_text())
    assert diag.get("exit_code") == 2
    assert "gh:" in diag.get("stderr_excerpt", "")
    assert "ghp_1234567890abcdefgh" not in diag.get("stderr_excerpt", "")
    assert "<redacted>" in diag.get("stderr_excerpt", "")


def test_token_values_are_redacted() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    raw = "GH_TOKEN=ghp_12345abc GITHUB_TOKEN=ghs_99999 OTHER_TOKEN=secret123"
    redacted = release_assurance.redact_text(raw)
    assert "ghp_12345abc" not in redacted
    assert "ghs_99999" not in redacted
    assert "secret123" not in redacted
    assert "<redacted>" in redacted


def test_arbitrary_secret_like_values_are_redacted() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    raw = "sk-12345678901234567890 Bearer abcdef1234567890 APCA-12345678-1234-1234-1234-123456789012"
    redacted = release_assurance.redact_text(raw)
    assert "sk-12345678901234567890" not in redacted
    assert "abcdef1234567890" not in redacted
    assert "APCA-12345678-1234-1234-1234-123456789012" not in redacted
    assert "<redacted>" in redacted


def test_account_ids_are_redacted() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    raw = "account 123e4567-e89b-12d3-a456-426614174000"
    redacted = release_assurance.redact_text(raw)
    assert "123e4567-e89b-12d3-a456-426614174000" not in redacted
    assert "<redacted>" in redacted


def test_diagnostics_json_is_created_when_flag_provided(tmp_path: Path) -> None:
    diagnostics_path = tmp_path / "diagnostics.json"
    result = _run_release_assurance(
        tmp_path,
        "--diagnostics-json",
        str(diagnostics_path),
    )
    assert diagnostics_path.exists(), result.stderr
    data = json.loads(diagnostics_path.read_text())
    assert data.get("schema_version") == "atlas-release-assurance-diagnostics/1.0"
    assert data.get("passed") is False
    assert data.get("release") == "v0.0.0-does-not-exist"
    assert "failed_check" in data


def test_diagnostics_json_contains_required_fields(tmp_path: Path) -> None:
    diagnostics_path = tmp_path / "diagnostics.json"
    result = _run_release_assurance(
        tmp_path,
        "--diagnostics-json",
        str(diagnostics_path),
    )
    assert diagnostics_path.exists(), result.stderr
    data = json.loads(diagnostics_path.read_text())
    for key in (
        "schema_version",
        "passed",
        "release",
        "failed_phase",
        "failed_check",
        "command",
        "exit_code",
        "stdout_excerpt",
        "stderr_excerpt",
        "remediation",
        "redactions_applied",
    ):
        assert key in data, f"missing {key}"


def test_diagnostics_json_does_not_contain_secret_values(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    data = {
        "schema_version": "atlas-release-assurance-diagnostics/1.0",
        "passed": False,
        "release": "v0.6.15",
        "failed_check": "github_release_present",
        "stdout_excerpt": "token=ghp_12345",
        "stderr_excerpt": "Authorization: Bearer abcdef",
        "redactions_applied": ["*_TOKEN"],
    }
    redacted = release_assurance.redact_text(json.dumps(data))
    assert "ghp_12345" not in redacted
    assert "abcdef" not in redacted


def test_success_path_summary_keys_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    def mock_run_cmd(cmd, check=True, cwd=None, env=None):
        text = " ".join(str(p) for p in cmd)
        if "git tag -l" in text:
            return "v0.6.15\n", 0, ""
        if "git ls-remote" in text:
            return "refs/tags/v0.6.15\n", 0, ""
        if "gh release view" in text:
            return '{"url":"https://github.com/usernotfinded/atlas-agent/releases/tag/v0.6.15"}', 0, ""
        if "update check --dry-run" in text:
            return "Current version: 0.6.15", 0, ""
        if "from atlas_agent.update.sources" in text:
            return "False", 0, ""
        if "audit-pack --help" in text or "verify-audit-pack --help" in text:
            return "", 0, ""
        if "git diff HEAD --name-only" in text:
            return "", 0, ""
        return "", 0, ""

    monkeypatch.setattr("release_assurance.run_cmd", mock_run_cmd)
    monkeypatch.setattr(
        "sys.argv",
        ["release_assurance.py", "--version", "v0.6.15", "--output", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        release_assurance.main()

    assert exc_info.value.code == 0
    summary_lines = [
        line
        for line in (tmp_path / "release-assurance-summary.json").read_text().splitlines()
        if line.startswith('  "')
    ]
    summary_keys = [line.split(": ", 1)[0].strip() for line in summary_lines]
    assert summary_keys[:4] == [
        '"artifact_type"',
        '"checks"',
        '"findings"',
        '"generated_at"',
    ]


def test_success_path_does_not_emit_failure_block_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import release_assurance

    def mock_run_cmd(cmd, check=True, cwd=None, env=None):
        text = " ".join(str(p) for p in cmd)
        if "git tag -l" in text:
            return "v0.6.15\n", 0, ""
        if "git ls-remote" in text:
            return "refs/tags/v0.6.15\n", 0, ""
        if "gh release view" in text:
            return '{"url":"https://github.com/usernotfinded/atlas-agent/releases/tag/v0.6.15"}', 0, ""
        if "update check --dry-run" in text:
            return "Current version: 0.6.15", 0, ""
        if "from atlas_agent.update.sources" in text:
            return "False", 0, ""
        if "audit-pack --help" in text or "verify-audit-pack --help" in text:
            return "", 0, ""
        if "git diff HEAD --name-only" in text:
            return "", 0, ""
        return "", 0, ""

    monkeypatch.setattr("release_assurance.run_cmd", mock_run_cmd)
    monkeypatch.setattr(
        "sys.argv",
        ["release_assurance.py", "--version", "v0.6.15", "--output", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        release_assurance.main()

    assert exc_info.value.code == 0
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary["valid"] is True


def test_existing_release_assurance_tests_still_pass() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_release_assurance.py", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_checker_passes_on_real_repo() -> None:
    result = check_diagnostics()
    assert result["passed"], f"Expected checker to pass, got errors: {result['errors']}"


def test_checker_fails_when_test_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_test = tmp_path / "missing_test_file.py"
    monkeypatch.setattr(
        "scripts.check_release_assurance_diagnostics.TEST_FILE", missing_test
    )
    result = check_diagnostics()
    assert not result["passed"]
    assert any("test file missing" in e.lower() for e in result["errors"])


def test_checker_fails_when_redact_text_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_release = tmp_path / "release_assurance.py"
    fake_release.write_text(
        "_REDACTION_PATTERNS = [\n"
        '    (re.compile(r\"\\bGH_TOKEN=\\S+\"), \"<redacted>\"),\n'
        "]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.check_release_assurance_diagnostics.RELEASE_ASSURANCE_SCRIPT",
        fake_release,
    )
    result = check_diagnostics()
    assert not result["passed"]
    assert any("redact_text" in e.lower() for e in result["errors"])
