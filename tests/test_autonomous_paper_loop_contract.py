#!/usr/bin/env python3
"""Tests for scripts/check_autonomous_paper_loop_contract.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_autonomous_paper_loop_contract.py"
DOC = REPO_ROOT / "docs" / "autonomous-paper-loop.md"


def _run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _build_fake_repo(tmp_path: Path, module_text: str) -> Path:
    """Create a fake repo with the checker and a synthetic autonomous_paper.py."""
    fake_repo = tmp_path / "fake_repo"
    fake_docs = fake_repo / "docs"
    fake_docs.mkdir(parents=True)

    if DOC.exists():
        (fake_docs / "autonomous-paper-loop.md").write_text(
            DOC.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        # Minimal doc that satisfies required phrases and cross references.
        (fake_docs / "autonomous-paper-loop.md").write_text(
            "\n".join(
                [
                    "paper-only local-first no live trading",
                    "no broker order submission RiskManager deterministic",
                    "not financial advice does **not** claim autonomous live trading readiness",
                    "atlas agent autonomous-paper",
                    "[bounded-live-autonomy-governance.md]",
                    "[shadow-live-readiness-contract.md]",
                ]
            ),
            encoding="utf-8",
        )

    (fake_docs / "shadow-live-readiness-contract.md").write_text("placeholder\n")

    fake_src = fake_repo / "src" / "atlas_agent" / "agent"
    fake_src.mkdir(parents=True)
    (fake_src / "autonomous_paper.py").write_text(module_text, encoding="utf-8")

    (fake_repo / "src" / "atlas_agent" / "cli.py").write_text(
        '"autonomous-paper"\n', encoding="utf-8"
    )

    (fake_repo / "tests").mkdir(parents=True, exist_ok=True)
    (fake_repo / "tests" / "test_autonomous_paper_loop.py").write_text(
        "# placeholder\n", encoding="utf-8"
    )

    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"
    fake_checker.parent.mkdir(parents=True)
    shutil.copy2(CHECKER, fake_checker)

    return fake_repo


@pytest.mark.skipif(not DOC.exists(), reason="Autonomous paper loop doc missing")
def test_checker_passes_on_real_repo() -> None:
    """The contract checker must pass against the real repository."""
    result = _run_checker()
    assert result.returncode == 0, f"Checker failed:\n{result.stdout}\n{result.stderr}"
    assert "PASSED" in result.stdout


@pytest.mark.skipif(not DOC.exists(), reason="Autonomous paper loop doc missing")
def test_checker_json_output() -> None:
    """The --json flag must emit a structured result."""
    result = _run_checker("--json")
    assert result.returncode == 0, f"Checker failed:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["errors"] == []


def test_checker_fails_when_forbidden_phrase_present(tmp_path: Path) -> None:
    """A temporary copy of the doc containing a forbidden phrase must fail."""
    if not DOC.exists():
        pytest.skip("Autonomous paper loop doc missing")

    fake_repo = tmp_path / "fake_repo"
    fake_docs = fake_repo / "docs"
    fake_docs.mkdir(parents=True)

    fake_doc = fake_docs / "autonomous-paper-loop.md"
    fake_doc.write_text(DOC.read_text(encoding="utf-8") + "\nThis is guaranteed profit.\n")

    # The checker only examines its own doc and the shadow contract doc. We
    # create a minimal shadow doc so the required-file check does not mask the
    # forbidden-phrase finding.
    (fake_docs / "shadow-live-readiness-contract.md").write_text("placeholder\n")

    # Copy the checker into the fake repo and run it there.
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"
    fake_checker.parent.mkdir(parents=True)
    shutil.copy2(CHECKER, fake_checker)

    result = subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("guaranteed profit" in err.lower() for err in payload["errors"])


def test_checker_fails_on_forbidden_import(tmp_path: Path) -> None:
    """A fake autonomous_paper.py importing a forbidden module must fail."""
    fake_repo = _build_fake_repo(tmp_path, "import atlas_agent.brokers\n")
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"

    result = subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("atlas_agent.brokers" in err for err in payload["errors"])


def test_checker_fails_on_place_order(tmp_path: Path) -> None:
    """A fake autonomous_paper.py containing a forbidden order submission pattern must fail."""
    fake_repo = _build_fake_repo(tmp_path, "broker.place_order(\n")
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"

    result = subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("place_order" in err for err in payload["errors"])


def test_checker_fails_on_live_trading_enabled_true(tmp_path: Path) -> None:
    """A fake autonomous_paper.py setting live_trading_enabled=True must fail."""
    fake_repo = _build_fake_repo(
        tmp_path, "limits = RiskLimits(live_trading_enabled=True)\n"
    )
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"

    result = subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("live_trading_enabled=True" in err for err in payload["errors"])


def test_checker_fails_on_credential_env_access(tmp_path: Path) -> None:
    """A fake autonomous_paper.py accessing credential env vars must fail."""
    fake_repo = _build_fake_repo(
        tmp_path, 'key = os.getenv("ALPACA_API_KEY")\n'
    )
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"

    result = subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("credential environment access" in err for err in payload["errors"])


def test_checker_imports_no_network_or_credentials() -> None:
    """The checker module must not import broker/provider/credential modules."""
    source = CHECKER.read_text(encoding="utf-8")
    forbidden = ["requests", "urllib", "alpaca", "openai", "boto", "paramiko"]
    import_lines = [
        line.lower()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any(name in line for line in import_lines for name in forbidden)
