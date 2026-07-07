"""Tests for paper-mode provider isolation (CAND-024).

Documentation/test-only. No real provider or broker calls.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_paper_provider_isolation.py"
DEMO_SCRIPT = ROOT / "scripts" / "demo_autonomous_paper_workflow.sh"
ISOLATION_DOC = ROOT / "docs" / "paper-provider-isolation.md"
AUTONOMOUS_DOC = ROOT / "docs" / "autonomous-paper-workflow.md"
GOVERNANCE_DOC = ROOT / "docs" / "bounded-live-autonomy-governance.md"
LIVE_SUBMIT_DOC = ROOT / "docs" / "live-submit-safety-contract.md"
PAPER_GUIDE_DOC = ROOT / "docs" / "paper-trading-guide.md"

PROVIDER_ENV_KEYS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY",
    "KIMI_API_KEY",
    "XAI_API_KEY",
    "GROK_API_KEY",
    "ATLAS_OPENROUTER_API_KEY",
    "ATLAS_OPENAI_API_KEY",
    "ATLAS_ANTHROPIC_API_KEY",
]


def _run_script(args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_paper_provider_isolation", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_paper_provider_isolation"] = mod
    spec.loader.exec_module(mod)
    return mod


def _scrubbed_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + (
        f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
    )
    for key in PROVIDER_ENV_KEYS:
        env.pop(key, None)
    return env


def _make_isolated_repo(
    *,
    omit_doc: bool = False,
    omit_script: bool = False,
    chmod_script: bool = True,
    script_patch: dict[str, str] | None = None,
    doc_patch: dict[str, tuple[str, str]] | None = None,
) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(dir=ROOT))

    docs_to_copy = [
        "docs/paper-provider-isolation.md",
        "docs/autonomous-paper-workflow.md",
        "docs/bounded-live-autonomy-governance.md",
        "docs/live-submit-safety-contract.md",
        "docs/paper-trading-guide.md",
    ]
    for rel in docs_to_copy:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = tmp_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not omit_doc or rel != "docs/paper-provider-isolation.md":
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    for rel in (
        "README.md",
        "docs/trust/README.md",
        "docs/reviewer-checklist.md",
    ):
        src = ROOT / rel
        if src.exists():
            dst = tmp_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    script_dst = tmp_dir / "scripts" / "demo_autonomous_paper_workflow.sh"
    script_dst.parent.mkdir(parents=True, exist_ok=True)
    if not omit_script:
        text = DEMO_SCRIPT.read_text(encoding="utf-8")
        if script_patch:
            for old, new in script_patch.items():
                text = text.replace(old, new)
        script_dst.write_text(text, encoding="utf-8")
        if chmod_script:
            os.chmod(script_dst, 0o755)

    release_metadata_src = ROOT / "scripts" / "release_metadata.py"
    if release_metadata_src.exists():
        (tmp_dir / "scripts" / "release_metadata.py").write_text(
            release_metadata_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
        metadata_src = ROOT / "docs" / "releases" / "release-metadata.json"
        metadata_dst = tmp_dir / "docs" / "releases" / "release-metadata.json"
        metadata_dst.parent.mkdir(parents=True, exist_ok=True)
        metadata_dst.write_text(metadata_src.read_text(encoding="utf-8"), encoding="utf-8")

    for rel in (
        "src/atlas_agent/providers/factory.py",
        "src/atlas_agent/agent/runner.py",
        "src/atlas_agent/cli.py",
    ):
        src = ROOT / rel
        dst = tmp_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    if doc_patch:
        for rel, (old, new) in doc_patch.items():
            doc_file = tmp_dir / rel
            if doc_file.exists():
                text = doc_file.read_text(encoding="utf-8").replace(old, new)
                doc_file.write_text(text, encoding="utf-8")

    checker_text = SCRIPT.read_text(encoding="utf-8")
    patched = checker_text.replace(
        "REPO_ROOT = Path(__file__).resolve().parent.parent",
        f'REPO_ROOT = Path("{tmp_dir}")',
    )
    tmp_checker = tmp_dir / "scripts" / "check_paper_provider_isolation.py"
    tmp_checker.parent.mkdir(parents=True, exist_ok=True)
    tmp_checker.write_text(patched, encoding="utf-8")
    os.chmod(tmp_checker, 0o755)

    return tmp_dir


def _run_isolated(tmp_dir: Path) -> subprocess.CompletedProcess[str]:
    checker = tmp_dir / "scripts" / "check_paper_provider_isolation.py"
    result = subprocess.run(
        [sys.executable, str(checker)],
        capture_output=True,
        text=True,
    )
    try:
        shutil.rmtree(tmp_dir)
    except OSError:
        pass
    return result


def _init_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "init", str(ws), "--template", "routine-trader"],
        cwd=ROOT,
        env=_scrubbed_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return ws


def _setup_workspace(ws: Path) -> None:
    env = _scrubbed_env()
    cmds = [
        [sys.executable, "-m", "atlas_agent.cli", "discipline", "setup", "--manual", "--yes"],
        [sys.executable, "-m", "atlas_agent.cli", "config", "set", "market.symbol", "ATLAS-DEMO"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


class TestCheckerOnCurrentRepo:
    def test_script_passes_on_repo(self) -> None:
        result = _run_script()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout

    def test_json_output(self) -> None:
        result = _run_script(["--json"])
        assert result.returncode == 0, result.stdout + result.stderr
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == "0.6.21"
        assert data["current_public_tag"] == "v0.6.21"
        assert data["next_planned_tag"] == "v0.6.22"
        assert data["pypi_published"] is False
        assert data["errors"] == []


class TestMissingFiles:
    def test_missing_isolation_doc_fails(self) -> None:
        tmp = _make_isolated_repo(omit_doc=True)
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "paper-provider-isolation.md" in result.stdout.lower()

    def test_missing_demo_script_fails(self) -> None:
        tmp = _make_isolated_repo(omit_script=True)
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "demo_autonomous_paper_workflow.sh" in result.stdout.lower()


class TestUnsafeScript:
    def test_provider_secret_pattern_fails(self) -> None:
        tmp = _make_isolated_repo(
            script_patch={
                "set -euo pipefail": "set -euo pipefail\nANTHROPIC_API_KEY=sk-test1234567890\n"
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "secret" in result.stdout.lower()


class TestUnsafeDocs:
    def test_autonomous_live_trading_ready_fails(self) -> None:
        tmp = _make_isolated_repo(
            doc_patch={
                "docs/paper-provider-isolation.md": (
                    "## Live mode remains fail-closed",
                    "## Live mode: this proves autonomous live trading ready",
                )
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "autonomous live trading ready" in result.stdout.lower()

    def test_guaranteed_profit_fails(self) -> None:
        tmp = _make_isolated_repo(
            doc_patch={
                "docs/paper-provider-isolation.md": (
                    "Not financial advice",
                    "guaranteed profit",
                )
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "guaranteed profit" in result.stdout.lower()

    def test_v0613_released_claim_fails(self) -> None:
        tmp = _make_isolated_repo(
            doc_patch={
                "docs/paper-provider-isolation.md": (
                    "## Paper mode offline guarantee",
                    "## released v0.6.13",
                )
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "v0.6.13" in result.stdout.lower()


class TestCrossReferences:
    def test_missing_link_from_autonomous_doc_fails(self) -> None:
        tmp = _make_isolated_repo(
            doc_patch={
                "docs/autonomous-paper-workflow.md": (
                    "[Paper Mode Provider Isolation](paper-provider-isolation.md)",
                    "",
                )
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "paper-provider-isolation.md" in result.stdout.lower()


class TestImplementationWiring:
    def test_missing_null_branch_fails(self) -> None:
        tmp = _make_isolated_repo()
        factory = tmp / "src" / "atlas_agent" / "providers" / "factory.py"
        text = factory.read_text(encoding="utf-8")
        text = text.replace('provider_id == "null"', 'provider_id == "__null__"')
        factory.write_text(text, encoding="utf-8")
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert '"null" provider branch' in result.stdout


class TestRuntimeIsolation:
    def test_paper_offline_run_completes(self, tmp_path: Path) -> None:
        ws = _init_workspace(tmp_path)
        _setup_workspace(ws)
        result = subprocess.run(
            [sys.executable, "-m", "atlas_agent.cli", "run", "--mode", "paper", "--offline", "--symbol", "ATLAS-DEMO", "--max-cycles", "1"],
            cwd=ws,
            env=_scrubbed_env(),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_paper_fallback_without_credentials_completes(self, tmp_path: Path, caplog) -> None:
        ws = _init_workspace(tmp_path)
        _setup_workspace(ws)
        env = _scrubbed_env()
        result = subprocess.run(
            [sys.executable, "-m", "atlas_agent.cli", "run", "--mode", "paper", "--symbol", "ATLAS-DEMO", "--max-cycles", "1"],
            cwd=ws,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "Falling back to the offline NullProvider" in result.stderr

    def test_no_network_provider_called_when_offline(self, tmp_path: Path, monkeypatch) -> None:
        ws = _init_workspace(tmp_path)
        _setup_workspace(ws)
        called: list[str] = []

        def _fail_if_called(*args, **kwargs):
            called.append("complete")
            raise AssertionError("Real provider.complete should not be called in offline mode")

        from atlas_agent.providers import openai_compatible, anthropic
        monkeypatch.setattr(openai_compatible.OpenAICompatibleProvider, "complete", _fail_if_called)
        monkeypatch.setattr(anthropic.AnthropicProvider, "complete", _fail_if_called)

        result = subprocess.run(
            [sys.executable, "-m", "atlas_agent.cli", "run", "--mode", "paper", "--offline", "--symbol", "ATLAS-DEMO", "--max-cycles", "1"],
            cwd=ws,
            env=_scrubbed_env(),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert called == []

    def test_live_mode_fails_safely(self, tmp_path: Path) -> None:
        ws = _init_workspace(tmp_path)
        _setup_workspace(ws)
        result = subprocess.run(
            [sys.executable, "-m", "atlas_agent.cli", "run", "--mode", "live", "--symbol", "ATLAS-DEMO", "--max-cycles", "1"],
            cwd=ws,
            env=_scrubbed_env(),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


class TestCheckerDoesNotMutate:
    def test_no_write_calls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "write_text" not in text
        assert '"w"' not in text
        assert "'w'" not in text

    def test_no_network_imports(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "import requests" not in text
        assert "import urllib" not in text
        assert "import httpx" not in text
        assert "import socket" not in text


class TestUnitFunctions:
    def test_module_loads(self) -> None:
        mod = _load_checker_module()
        assert hasattr(mod, "main")
        assert callable(mod.main)

    def test_required_files_pass(self) -> None:
        mod = _load_checker_module()
        errors = mod._check_required_files()
        assert errors == []
