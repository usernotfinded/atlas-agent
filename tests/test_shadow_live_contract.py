"""Tests for the shadow-live / read-only readiness contract checker (CAND-001).

Documentation/test-only. No execution code, no network calls, no credentials,
no provider SDKs, no broker changes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_shadow_live_contract.py"
CONTRACT_DOC = REPO_ROOT / "docs" / "shadow-live-readiness-contract.md"
GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"


def _run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _run_checker_with_patched_doc(original_text: str, patched_text: str) -> subprocess.CompletedProcess[str]:
    """Run the checker with a patched contract doc inside a temp dir under REPO_ROOT."""
    tmp_dir = Path(tempfile.mkdtemp(dir=REPO_ROOT))
    try:
        # Copy required files into temp repo structure
        tmp_contract = tmp_dir / "docs" / "shadow-live-readiness-contract.md"
        tmp_contract.parent.mkdir(parents=True, exist_ok=True)
        tmp_contract.write_text(patched_text, encoding="utf-8")

        tmp_governance = tmp_dir / "docs" / "bounded-live-autonomy-governance.md"
        shutil.copy2(str(GOVERNANCE_DOC), str(tmp_governance))

        # Patch checker to use temp dir as REPO_ROOT
        original_script = CHECKER_SCRIPT.read_text(encoding="utf-8")
        patched_script = original_script.replace(
            'REPO_ROOT = Path(__file__).resolve().parent.parent',
            f'REPO_ROOT = Path("{tmp_dir}")',
        )
        tmp_script = tmp_dir / "check_shadow_live_contract.py"
        tmp_script.write_text(patched_script, encoding="utf-8")

        return subprocess.run(
            [sys.executable, str(tmp_script)],
            capture_output=True,
            text=True,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class TestCheckerExists:
    def test_script_exists_and_is_executable(self) -> None:
        assert CHECKER_SCRIPT.exists(), f"Checker not found: {CHECKER_SCRIPT}"
        assert CHECKER_SCRIPT.stat().st_mode & 0o111, "Checker should be executable"
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env python3"), "Checker missing python3 shebang"


class TestCheckerPassesOnCurrentRepo:
    def test_checker_passes(self) -> None:
        result = _run_checker()
        assert result.returncode == 0, (
            f"Shadow-live contract checker failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASSED" in result.stdout


class TestCheckerJsonOutput:
    def test_json_output_passes(self) -> None:
        result = _run_checker("--json")
        assert result.returncode == 0, (
            f"JSON checker failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["errors"] == []

    def test_json_output_has_expected_keys(self) -> None:
        result = _run_checker("--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "passed" in data
        assert "errors" in data


class TestCheckerRejectsForbiddenClaims:
    def test_rejects_guaranteed_profit_in_contract_doc(self) -> None:
        original = CONTRACT_DOC.read_text(encoding="utf-8")
        injected = original + "\n\nThis mode produces guaranteed profit.\n"
        result = _run_checker_with_patched_doc(original, injected)
        assert result.returncode != 0, "Expected failure on forbidden claim injection"
        assert "guaranteed profit" in result.stdout.lower()

    def test_rejects_autonomous_live_trading_ready(self) -> None:
        original = CONTRACT_DOC.read_text(encoding="utf-8")
        injected = original + "\n\nAtlas is autonomous live trading ready.\n"
        result = _run_checker_with_patched_doc(original, injected)
        assert result.returncode != 0
        assert "autonomous live trading ready" in result.stdout.lower()


class TestCheckerDoesNotExecute:
    def test_no_network_calls(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "import requests" not in text
        assert "import urllib" not in text
        assert "import httpx" not in text
        assert "import socket" not in text
        assert "from requests" not in text
        assert "from urllib" not in text
        assert "from httpx" not in text

    def test_no_credential_loading(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "load_dotenv" not in text
        assert "getenv(" not in text
        assert "os.environ" not in text
        assert "environ[" not in text

    def test_no_subprocess_calls(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "subprocess.run" not in text
        assert "subprocess.call" not in text
        assert "os.system" not in text
        assert "Popen" not in text
