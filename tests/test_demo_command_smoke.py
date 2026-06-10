"""Tests for demo command smoke checker — CAND-004.

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


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_demo_command_smoke.py"
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_paper_workflow.sh"
CHECK_DEMO_PROOF = REPO_ROOT / "scripts" / "check_demo_proof.py"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.json"
CANDIDATES_MD = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.md"


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_demo_command_smoke", CHECKER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_demo_command_smoke"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_checker_in_isolated_repo(
    *,
    omit_demo_script: bool = False,
    demo_patch: dict[str, str] | None = None,
    doc_patch: dict[str, tuple[str, str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the checker with REPO_ROOT patched to a temp dir."""
    tmp_dir = Path(tempfile.mkdtemp(dir=REPO_ROOT))

    # Copy docs directory
    docs_src = REPO_ROOT / "docs"
    if docs_src.exists():
        shutil.copytree(str(docs_src), str(tmp_dir / "docs"), dirs_exist_ok=True)

    # Copy README
    readme_src = REPO_ROOT / "README.md"
    if readme_src.exists():
        (tmp_dir / "README.md").write_text(
            readme_src.read_text(encoding="utf-8"), encoding="utf-8"
        )

    # Copy scripts/check_demo_proof.py so the checker finds it
    proof_dst = tmp_dir / "scripts" / "check_demo_proof.py"
    proof_dst.parent.mkdir(parents=True, exist_ok=True)
    if CHECK_DEMO_PROOF.exists():
        shutil.copy2(str(CHECK_DEMO_PROOF), str(proof_dst))

    # Copy and optionally patch demo script
    demo_dst = tmp_dir / "scripts" / "demo_paper_workflow.sh"
    demo_dst.parent.mkdir(parents=True, exist_ok=True)
    if not omit_demo_script:
        text = DEMO_SCRIPT.read_text(encoding="utf-8")
        if demo_patch:
            for old, new in demo_patch.items():
                text = text.replace(old, new)
        demo_dst.write_text(text, encoding="utf-8")
        os.chmod(str(demo_dst), 0o755)

    # Optionally patch docs
    if doc_patch:
        for rel_path, (old, new) in doc_patch.items():
            doc_file = tmp_dir / rel_path
            if doc_file.exists():
                text = doc_file.read_text(encoding="utf-8").replace(old, new)
                doc_file.write_text(text, encoding="utf-8")

    # Patch checker REPO_ROOT and run
    checker_text = CHECKER_SCRIPT.read_text(encoding="utf-8")
    patched = checker_text.replace(
        'REPO_ROOT = Path(__file__).resolve().parent.parent',
        f'REPO_ROOT = Path("{tmp_dir}")',
    )
    tmp_checker = tmp_dir / "scripts" / "check_demo_command_smoke.py"
    tmp_checker.parent.mkdir(parents=True, exist_ok=True)
    tmp_checker.write_text(patched, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(tmp_checker)],
        capture_output=True,
        text=True,
    )

    # Cleanup
    try:
        shutil.rmtree(str(tmp_dir))
    except OSError:
        pass

    return result


class TestCheckerExists:
    def test_script_exists_and_is_executable(self) -> None:
        assert CHECKER_SCRIPT.exists(), f"Checker not found: {CHECKER_SCRIPT}"
        assert os.access(CHECKER_SCRIPT, os.X_OK), "Checker is not executable"
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env python3"), "Checker missing python3 shebang"


class TestCheckerPassesOnCurrentRepo:
    def test_checker_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECKER_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Demo command smoke checker failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASSED" in result.stdout


class TestCheckerRejectsMissingDemoScript:
    def test_rejects_missing_demo_script(self) -> None:
        result = _run_checker_in_isolated_repo(omit_demo_script=True)
        assert result.returncode != 0, "Expected failure when demo script is missing"
        assert "demo script not found" in result.stdout.lower()


class TestCheckerRejectsMissingCanonicalDocLink:
    def test_rejects_missing_canonical_doc_link(self) -> None:
        patch = {
            "README.md": ("./scripts/demo_paper_workflow.sh", "./scripts/demo_paper_workflow_MISSING.sh"),
            "docs/demo-paper-workflow.md": (
                "./scripts/demo_paper_workflow.sh",
                "./scripts/demo_paper_workflow_MISSING.sh",
            ),
            "docs/external-reviewer-walkthrough.md": (
                "./scripts/demo_paper_workflow.sh",
                "./scripts/demo_paper_workflow_MISSING.sh",
            ),
        }
        result = _run_checker_in_isolated_repo(doc_patch=patch)
        assert result.returncode != 0, (
            "Expected failure when canonical doc link is missing"
        )
        assert "canonical command" in result.stdout.lower()


class TestCheckerRejectsForbiddenPatterns:
    def test_rejects_live_mode_in_demo(self) -> None:
        result = _run_checker_in_isolated_repo(
            demo_patch={"--mode paper": "--mode live"}
        )
        assert result.returncode != 0, (
            "Expected failure on forbidden live mode pattern"
        )
        assert "forbidden" in result.stdout.lower()

    def test_rejects_rm_rf_in_demo(self) -> None:
        result = _run_checker_in_isolated_repo(
            demo_patch={
                "set -euo pipefail": "set -euo pipefail\nrm -rf /tmp/demo\n"
            }
        )
        assert result.returncode != 0, (
            "Expected failure on forbidden rm -rf pattern"
        )
        assert "forbidden" in result.stdout.lower()

    def test_rejects_curl_in_demo(self) -> None:
        result = _run_checker_in_isolated_repo(
            demo_patch={
                "set -euo pipefail": "set -euo pipefail\ncurl https://example.com\n"
            }
        )
        assert result.returncode != 0, "Expected failure on forbidden curl pattern"
        assert "forbidden" in result.stdout.lower()


class TestCheckerRejectsMissingPaperLocalWording:
    def test_rejects_missing_paper_wording(self) -> None:
        result = _run_checker_in_isolated_repo(demo_patch={"paper": "generic", "--dry-run": "", "paper-only": ""})
        assert result.returncode != 0, (
            "Expected failure on missing paper/local wording"
        )
        assert "paper" in result.stdout.lower() or "local" in result.stdout.lower()


class TestCheckerDoesNotExecuteDemo:
    def test_no_subprocess_call_to_demo_script(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "os.system" not in text
        assert "subprocess.call" not in text
        assert "subprocess.run" not in text
        assert "Popen" not in text

    def test_no_network_calls(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "import requests" not in text
        assert "import urllib" not in text
        assert "import httpx" not in text
        assert "import socket" not in text
        assert "from requests" not in text
        assert "from urllib" not in text
        assert "from httpx" not in text


class TestCheckerSourceIsClean:
    def test_no_import_of_provider_broker_modules(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "import alpaca" not in text.lower()
        assert "import binance" not in text.lower()
        assert "import openai" not in text.lower()
        assert "import anthropic" not in text.lower()

    def test_no_pypi_or_release_imports(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        assert "import twine" not in text.lower()
        assert "from twine" not in text.lower()
        assert "import gh" not in text.lower()


class TestSmokeCheckIncludesChecker:
    def test_smoke_check_includes_checker(self) -> None:
        text = (REPO_ROOT / "scripts" / "smoke_check.sh").read_text(encoding="utf-8")
        assert "check_demo_command_smoke.py" in text


class TestLocalQuickCheckIncludesChecker:
    def test_local_quick_check_includes_checker(self) -> None:
        text = (REPO_ROOT / "scripts" / "local_quick_check.sh").read_text(
            encoding="utf-8"
        )
        assert "check_demo_command_smoke.py" in text


class TestCandidateTracking:
    def test_cand_004_implemented_in_json(self) -> None:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        candidates = {c["id"]: c for c in data.get("candidates", [])}
        assert "CAND-004" in candidates, "CAND-004 missing from candidates JSON"
        assert candidates["CAND-004"].get("implemented") is True

    def test_cand_004_implemented_in_md(self) -> None:
        text = CANDIDATES_MD.read_text(encoding="utf-8")
        in_accepted = False
        for line in text.splitlines():
            if "## Accepted Candidates" in line:
                in_accepted = True
            elif line.startswith("## "):
                in_accepted = False
            if in_accepted and "CAND-004" in line:
                assert "implemented" in line.lower(), (
                    f"CAND-004 not marked implemented: {line}"
                )
                assert "not yet implemented" not in line.lower(), (
                    f"CAND-004 still marked not yet implemented: {line}"
                )
                return
        raise AssertionError("CAND-004 not found in Accepted Candidates section")

    def test_cand_001_002_003_still_implemented(self) -> None:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        candidates = {c["id"]: c for c in data.get("candidates", [])}
        for cand_id in ("CAND-001", "CAND-002", "CAND-003"):
            assert candidates[cand_id].get("implemented") is True, (
                f"{cand_id} no longer marked implemented"
            )


class TestCheckerUnitFunctions:
    def test_module_loads_and_has_main(self) -> None:
        mod = _load_checker_module()
        assert hasattr(mod, "main")
        assert callable(mod.main)

    def test_forbidden_patterns_detected(self) -> None:
        mod = _load_checker_module()
        assert mod._check_forbidden_patterns("safe text") == []
        assert mod._check_forbidden_patterns("curl https://example.com") != []
        assert mod._check_forbidden_patterns("--mode live") != []

    def test_paper_wording_detected(self) -> None:
        mod = _load_checker_module()
        assert mod._check_paper_wording("run --mode paper --dry-run") == []
        assert mod._check_paper_wording("run --mode live") != []
