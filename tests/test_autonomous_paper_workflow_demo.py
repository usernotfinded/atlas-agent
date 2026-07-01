"""Tests for the autonomous paper workflow demo checker (CAND-023).

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
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
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_autonomous_paper_workflow_demo.py"
DEMO_SCRIPT = ROOT / "scripts" / "demo_autonomous_paper_workflow.sh"
DEMO_DOC = ROOT / "docs" / "autonomous-paper-workflow.md"
GOVERNANCE_DOC = ROOT / "docs" / "bounded-live-autonomy-governance.md"
ROADMAP_DOC = ROOT / "docs" / "autonomy-roadmap.md"


def _run_script(args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_autonomous_paper_workflow_demo", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_autonomous_paper_workflow_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_isolated_repo(
    *,
    omit_doc: bool = False,
    omit_script: bool = False,
    chmod_script: bool = True,
    script_patch: dict[str, str] | None = None,
    doc_patch: dict[str, tuple[str, str]] | None = None,
) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(dir=ROOT))

    for rel in (
        "docs/autonomous-paper-workflow.md",
        "docs/bounded-live-autonomy-governance.md",
        "docs/autonomy-roadmap.md",
    ):
        src = ROOT / rel
        dst = tmp_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not omit_doc or rel != "docs/autonomous-paper-workflow.md":
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    for rel in ("README.md", "docs/public-launch-readiness.md", "docs/trust/README.md", "docs/reviewer-checklist.md"):
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

    # Copy release_metadata helper so the isolated checker can import it.
    release_metadata_src = ROOT / "scripts" / "release_metadata.py"
    if release_metadata_src.exists():
        (tmp_dir / "scripts" / "release_metadata.py").write_text(
            release_metadata_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
        # Copy metadata file too.
        metadata_src = ROOT / "docs" / "releases" / "release-metadata.json"
        metadata_dst = tmp_dir / "docs" / "releases" / "release-metadata.json"
        metadata_dst.parent.mkdir(parents=True, exist_ok=True)
        metadata_dst.write_text(metadata_src.read_text(encoding="utf-8"), encoding="utf-8")

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
    tmp_checker = tmp_dir / "scripts" / "check_autonomous_paper_workflow_demo.py"
    tmp_checker.parent.mkdir(parents=True, exist_ok=True)
    tmp_checker.write_text(patched, encoding="utf-8")
    os.chmod(tmp_checker, 0o755)

    return tmp_dir


def _run_isolated(tmp_dir: Path) -> subprocess.CompletedProcess[str]:
    checker = tmp_dir / "scripts" / "check_autonomous_paper_workflow_demo.py"
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
        assert data["package_version"] == "0.6.19"
        assert data["current_public_tag"] == "v0.6.19"
        assert data["next_planned_tag"] == "v0.6.20"
        assert data["errors"] == []


class TestMissingFiles:
    def test_missing_demo_doc_fails(self) -> None:
        tmp = _make_isolated_repo(omit_doc=True)
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "autonomous-paper-workflow.md" in result.stdout.lower()

    def test_missing_demo_script_fails(self) -> None:
        tmp = _make_isolated_repo(omit_script=True)
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "demo_autonomous_paper_workflow.sh" in result.stdout.lower()


class TestUnsafeScript:
    def test_non_executable_script_fails(self) -> None:
        tmp = _make_isolated_repo(chmod_script=False)
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "not executable" in result.stdout.lower()

    def test_enable_live_submit_fails(self) -> None:
        tmp = _make_isolated_repo(
            script_patch={"set -euo pipefail": "set -euo pipefail\nenable_live_submit=true\n"}
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "enable_live_submit" in result.stdout.lower()

    def test_enable_live_trading_fails(self) -> None:
        tmp = _make_isolated_repo(
            script_patch={"set -euo pipefail": "set -euo pipefail\nenable_live_trading=true\n"}
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "enable_live_trading" in result.stdout.lower()

    def test_trading_mode_live_fails(self) -> None:
        tmp = _make_isolated_repo(
            script_patch={"set -euo pipefail": "set -euo pipefail\nTRADING_MODE=live\n"}
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "trading_mode=live" in result.stdout.lower()

    def test_provider_secret_pattern_fails(self) -> None:
        tmp = _make_isolated_repo(
            script_patch={
                "set -euo pipefail": "set -euo pipefail\nANTHROPIC_API_KEY=sk-test1234567890\n"
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "secret" in result.stdout.lower()

    def test_broker_secret_pattern_fails(self) -> None:
        tmp = _make_isolated_repo(
            script_patch={
                "set -euo pipefail": "set -euo pipefail\nALPACA_API_KEY=APCA-1234567890ABCDEF\n"
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "secret" in result.stdout.lower()


class TestUnsafeDocs:
    def test_autonomous_live_trading_ready_fails(self) -> None:
        tmp = _make_isolated_repo(
            doc_patch={
                "docs/autonomous-paper-workflow.md": (
                    "does **not** claim autonomous-live-trading-readiness",
                    "this demo proves autonomous live trading ready",
                )
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "autonomous live trading ready" in result.stdout.lower()

    def test_guaranteed_profit_fails(self) -> None:
        tmp = _make_isolated_repo(
            doc_patch={
                "docs/autonomous-paper-workflow.md": (
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
                "docs/autonomous-paper-workflow.md": (
                    "planning/demo documentation",
                    "released v0.6.13",
                )
            }
        )
        result = _run_isolated(tmp)
        assert result.returncode != 0
        assert "v0.6.13" in result.stdout.lower()


class TestCheckerDoesNotMutate:
    def test_no_write_calls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "write_text" not in text
        # The checker only reads files; it never opens files for writing.
        assert '"w"' not in text
        assert "'w'" not in text
        assert "open(path" in text or "_read(path" in text

    def test_no_subprocess_execution(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "subprocess.run" in text  # only for git tag check
        assert "subprocess.call" not in text
        assert "os.system" not in text
        assert "Popen" not in text

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

    def test_demo_script_passes(self) -> None:
        mod = _load_checker_module()
        errors = mod._check_demo_script()
        assert errors == []

    def test_demo_script_detects_forbidden(self) -> None:
        mod = _load_checker_module()
        safe = DEMO_SCRIPT.read_text(encoding="utf-8")
        unsafe = safe.replace(
            "set -euo pipefail",
            "set -euo pipefail\nenable_live_submit=true\n",
        )
        tmp = Path(tempfile.mkdtemp(dir=ROOT))
        fake_script = tmp / "demo_autonomous_paper_workflow.sh"
        fake_script.write_text(unsafe, encoding="utf-8")
        os.chmod(fake_script, 0o755)
        with patch.object(mod, "DEMO_SCRIPT", fake_script):
            errors = mod._check_demo_script()
            assert any("enable_live_submit" in e for e in errors)
        shutil.rmtree(tmp)

    def test_doc_safety(self) -> None:
        mod = _load_checker_module()
        safe = (
            "# Doc\n\nPaper-only. Not financial advice. "
            "This doc does **not** claim autonomous-live-trading-readiness.\n"
        )
        errors = mod._check_forbidden_doc_claims()
        assert isinstance(errors, list)

    def test_release_metadata(self) -> None:
        mod = _load_checker_module()
        errors = mod._check_release_metadata()
        assert errors == []
