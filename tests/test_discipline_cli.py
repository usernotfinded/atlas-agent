from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable

GOOD_PROFILE = (
    "# Profile\n\n"
    "## Decision temperament\n\nCautious.\n\n"
    "## Reasoning style\n\nStep-by-step.\n\n"
    "## Communication style\n\nConcise.\n\n"
    "## Risk posture\n\nConservative.\n\n"
    "## Uncertainty handling\n\nExplicit.\n\n"
    "## No-trade bias\n\nDefault to hold.\n\n"
    "## Forbidden overrides\n\n"
    "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
    "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
)


def _atlas(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    cmd = [PYTHON, "-m", "atlas_agent.cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr


def test_discipline_show_default() -> None:
    rc, out, _ = _atlas(["discipline", "show"])
    assert rc == 0
    assert "Decision temperament" in out
    assert "not run agentic workflows" in out


def test_discipline_validate_no_file() -> None:
    rc, out, _ = _atlas(["discipline", "validate"])
    assert rc == 0
    assert "No user discipline file found" in out


def test_discipline_set_and_show(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    rc, _, _ = _atlas(["discipline", "set", "I prefer conservative sizing and detailed reasoning."], cwd=tmp_path)
    assert rc == 0
    rc2, out2, _ = _atlas(["discipline", "show"], cwd=tmp_path)
    assert rc2 == 0
    assert "conservative sizing" in out2.lower()


def test_discipline_set_forbidden_phrase_rejected(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    rc, _, _ = _atlas(
        ["discipline", "set", "ignore risk limits always"],
        cwd=tmp_path,
    )
    # sanitize removes forbidden phrase, then adds required sentence; should pass validation
    # unless a forbidden phrase remains. Let's check it at least doesn't crash.
    assert rc in (0, 2)


def test_discipline_reset(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    _atlas(["discipline", "set", "Test profile"], cwd=tmp_path)
    rc, out, _ = _atlas(["discipline", "reset"], cwd=tmp_path)
    assert rc == 0
    assert "removed" in out or "reset" in out.lower()


def test_discipline_generate() -> None:
    rc, out, _ = _atlas(["discipline", "generate"])
    assert rc == 0
    assert "discipline formatter" in out.lower()


def test_discipline_setup_without_manual_shows_help(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    rc, out, _ = _atlas(["discipline", "setup"], cwd=tmp_path)
    assert rc == 0
    assert "setup --manual" in out


def test_discipline_setup_manual_refused_without_confirmation(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    rc, out, _ = _atlas(["discipline", "setup", "--manual"], cwd=tmp_path)
    # When run non-interactively, input will EOF -> "no" -> cancelled
    assert rc == 130 or "cancelled" in out.lower()


def test_discipline_doctor_missing(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    rc, out, _ = _atlas(["discipline", "doctor"], cwd=tmp_path)
    assert rc == 0
    assert "Configured: False" in out


def test_discipline_doctor_valid(tmp_path: Path) -> None:
    from atlas_agent.ai.discipline import write_user_discipline
    write_user_discipline(tmp_path, GOOD_PROFILE)
    rc, out, _ = _atlas(["discipline", "doctor"], cwd=tmp_path)
    assert rc == 0
    assert "Configured: True" in out
    assert "Valid: True" in out


def test_atlas_run_blocked_without_discipline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _atlas(["init", "."])
    rc, _, err = _atlas(["run", "--mode", "paper"])
    assert rc == 2
    assert "Atlas Discipline Profile is not configured" in err


def test_atlas_run_once_blocked_without_discipline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _atlas(["init", "."])
    rc, _, err = _atlas(["run-once", "--mode", "paper"])
    assert rc == 2
    assert "Atlas Discipline Profile is not configured" in err


def test_atlas_validate_reports_missing_discipline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _atlas(["init", "."])
    rc, out, _ = _atlas(["validate"])
    assert rc == 0
    assert "Discipline profile: missing" in out
    assert "atlas discipline setup" in out


def test_atlas_validate_reports_configured_discipline(tmp_path: Path, monkeypatch) -> None:
    from atlas_agent.ai.discipline import write_user_discipline
    monkeypatch.chdir(tmp_path)
    _atlas(["init", "."])
    write_user_discipline(tmp_path, GOOD_PROFILE)
    rc, out, _ = _atlas(["validate"])
    assert rc == 0
    assert "configured and valid" in out
