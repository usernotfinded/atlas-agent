#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_loop_contract.py
# PURPOSE: Verifies autonomous paper loop contract behavior and regression
#         expectations.
# DEPS:    json, shutil, subprocess, sys, pathlib, pytest.
# ==============================================================================

"""Tests for scripts/check_autonomous_paper_loop_contract.py."""

# --- IMPORTS ---

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_autonomous_paper_loop_contract.py"
DOC = REPO_ROOT / "docs" / "autonomous-paper-loop.md"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _run_fake_checker(fake_repo: Path) -> subprocess.CompletedProcess:
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"
    return subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )


def _build_fake_repo(tmp_path: Path, module_text: str) -> Path:
    """Create a fake repo with the checker and a synthetic autonomous_paper.py.

    The provided ``module_text`` is written into ``autonomous_paper.py``;
    sibling autonomous-paper modules are created as empty placeholders so the
    required-files check passes.
    """
    return _build_fake_repo_with_module(
        tmp_path, "autonomous_paper.py", module_text
    )


def _build_fake_repo_with_module(
    tmp_path: Path, module_name: str, module_text: str
) -> Path:
    """Create a fake repo with ``module_text`` in the named module file.

    ``module_name`` must be one of the five autonomous-paper module file names.
    All other autonomous-paper modules are created as empty placeholders so the
    required-files check passes.
    """
    valid_modules = {
        "autonomous_paper.py",
        "autonomous_paper_kernel.py",
        "autonomous_paper_runner.py",
        "autonomous_paper_metrics.py",
        "autonomous_paper_models.py",
        "autonomous_paper_lock.py",
    }
    if module_name not in valid_modules:
        raise ValueError(f"Unsupported module name: {module_name}")

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
    (fake_docs / "bounded-live-autonomy-governance.md").write_text(
        "placeholder governance doc\n", encoding="utf-8"
    )

    fake_src = fake_repo / "src" / "atlas_agent" / "agent"
    fake_src.mkdir(parents=True)
    for name in valid_modules:
        (fake_src / name).write_text(
            module_text if name == module_name else "# placeholder\n",
            encoding="utf-8",
        )

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
    fake_repo = _build_fake_repo(tmp_path, "# placeholder\n")

    fake_doc = fake_repo / "docs" / "autonomous-paper-loop.md"
    text = fake_doc.read_text(encoding="utf-8")
    fake_doc.write_text(text + "\nThis is guaranteed profit.\n", encoding="utf-8")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("guaranteed profit" in err.lower() for err in payload["errors"])


def test_checker_fails_on_forbidden_import(tmp_path: Path) -> None:
    """A fake autonomous_paper.py importing a forbidden module must fail."""
    fake_repo = _build_fake_repo(tmp_path, "import atlas_agent.brokers\n")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("atlas_agent.brokers" in err for err in payload["errors"])


def test_checker_fails_on_place_order(tmp_path: Path) -> None:
    """A fake autonomous_paper.py containing a forbidden order submission pattern must fail."""
    fake_repo = _build_fake_repo(tmp_path, "broker.place_order(\n")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("place_order" in err for err in payload["errors"])


def test_checker_fails_on_live_trading_enabled_true(tmp_path: Path) -> None:
    """A fake autonomous_paper.py setting live_trading_enabled=True must fail."""
    fake_repo = _build_fake_repo(
        tmp_path, "limits = RiskLimits(live_trading_enabled=True)\n"
    )

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("live_trading_enabled=True" in err for err in payload["errors"])


def test_checker_fails_on_credential_env_access(tmp_path: Path) -> None:
    """A fake autonomous_paper.py accessing credential env vars must fail."""
    fake_repo = _build_fake_repo(
        tmp_path, 'key = os.getenv("ALPACA_API_KEY")\n'
    )

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("credential environment access" in err for err in payload["errors"])


def test_checker_fails_on_credential_environ_get_access(tmp_path: Path) -> None:
    """A fake autonomous_paper.py using os.environ.get('ALPACA_API_KEY') must fail."""
    fake_repo = _build_fake_repo(
        tmp_path, 'key = os.environ.get("ALPACA_API_KEY")\n'
    )

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("credential environment access" in err for err in payload["errors"])


def test_checker_fails_on_broker_resolver(tmp_path: Path) -> None:
    """A fake autonomous_paper.py instantiating BrokerResolver must fail."""
    fake_repo = _build_fake_repo(tmp_path, "resolver = BrokerResolver(\n")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("BrokerResolver(" in err for err in payload["errors"])


def test_checker_fails_on_provider_execute(tmp_path: Path) -> None:
    """A fake autonomous_paper.py calling provider.execute must fail."""
    fake_repo = _build_fake_repo(tmp_path, "result = provider.execute(\n")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("provider.execute" in err for err in payload["errors"])


def test_checker_fails_on_load_atlas_secrets(tmp_path: Path) -> None:
    """A fake autonomous_paper.py calling load_atlas_secrets must fail."""
    fake_repo = _build_fake_repo(tmp_path, "secrets = load_atlas_secrets(\n")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("load_atlas_secrets(" in err for err in payload["errors"])


def test_checker_fails_on_paper_only_false(tmp_path: Path) -> None:
    """A fake autonomous_paper.py setting paper_only=False must fail."""
    fake_repo = _build_fake_repo(tmp_path, "config = Config(paper_only=False)\n")

    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("paper_only=False" in err for err in payload["errors"])


def test_checker_fails_on_forbidden_import_in_kernel(tmp_path: Path) -> None:
    """A forbidden broker import in autonomous_paper_kernel.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_kernel.py", "import atlas_agent.brokers\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_kernel.py" in err and "atlas_agent.brokers" in err
        for err in payload["errors"]
    )


def test_checker_fails_on_forbidden_provider_import_in_runner(tmp_path: Path) -> None:
    """A forbidden provider import in autonomous_paper_runner.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_runner.py", "import atlas_agent.providers\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_runner.py" in err and "atlas_agent.providers" in err
        for err in payload["errors"]
    )


def test_checker_fails_on_forbidden_live_execution_import_in_metrics(tmp_path: Path) -> None:
    """A forbidden live execution import in autonomous_paper_metrics.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_metrics.py", "import atlas_agent.execution.live\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_metrics.py" in err and "atlas_agent.execution.live" in err
        for err in payload["errors"]
    )


def test_checker_fails_on_forbidden_credential_load_in_models(tmp_path: Path) -> None:
    """A forbidden credential loader in autonomous_paper_models.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_models.py", "secrets = load_atlas_secrets(\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_models.py" in err and "load_atlas_secrets(" in err
        for err in payload["errors"]
    )


def test_checker_fails_on_place_order_in_runner(tmp_path: Path) -> None:
    """A forbidden order submission in autonomous_paper_runner.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_runner.py", "broker.place_order(\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_runner.py" in err and "place_order" in err
        for err in payload["errors"]
    )


def test_checker_fails_on_cancel_order_in_kernel(tmp_path: Path) -> None:
    """A forbidden cancel-order pattern in autonomous_paper_kernel.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_kernel.py", "broker.cancel_order(\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_kernel.py" in err and "cancel_order" in err
        for err in payload["errors"]
    )


def test_checker_fails_on_forbidden_import_in_lock(tmp_path: Path) -> None:
    """A forbidden broker import in autonomous_paper_lock.py must be caught."""
    fake_repo = _build_fake_repo_with_module(
        tmp_path, "autonomous_paper_lock.py", "import atlas_agent.brokers\n"
    )
    result = _run_fake_checker(fake_repo)
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any(
        "autonomous_paper_lock.py" in err and "atlas_agent.brokers" in err
        for err in payload["errors"]
    )


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
