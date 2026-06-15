"""Tests for demo proof checker — CAND-002 and CAND-003.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_demo_proof.py"
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_paper_workflow.sh"
ARTIFACT_INDEX = REPO_ROOT / "docs" / "demo-artifact-index.md"
CANDIDATES_JSON = REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.json"


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_demo_proof", CHECKER_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_demo_proof"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_checker_with_patched_doc(original_text: str, patched_text: str, doc_name: str) -> subprocess.CompletedProcess[str]:
    """Run the checker with a single doc patched inside a temp dir under REPO_ROOT."""
    import shutil
    tmp_dir = Path(tempfile.mkdtemp(dir=REPO_ROOT))
    # Write the patched doc
    tmp_doc = tmp_dir / doc_name
    tmp_doc.parent.mkdir(parents=True, exist_ok=True)
    tmp_doc.write_text(patched_text, encoding="utf-8")

    # Copy other required files so the checker still finds them
    required_files = {
        "scripts/demo_paper_workflow.sh": DEMO_SCRIPT,
        "docs/demo-artifact-index.md": ARTIFACT_INDEX,
        "docs/demo-paper-workflow.md": REPO_ROOT / "docs" / "demo-paper-workflow.md",
        "docs/external-reviewer-walkthrough.md": REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
        "docs/reviewer-golden-path.md": REPO_ROOT / "docs" / "reviewer-golden-path.md",
        "README.md": REPO_ROOT / "README.md",
        "docs/trust/README.md": REPO_ROOT / "docs" / "trust" / "README.md",
        "docs/brokers.md": REPO_ROOT / "docs" / "brokers.md",
        "docs/releases/v0.6.8-candidates.md": REPO_ROOT / "docs" / "releases" / "v0.6.8-candidates.md",
        "docs/releases/v0.6.8-candidates.json": CANDIDATES_JSON,
    }
    for rel_path, src in required_files.items():
        if rel_path == doc_name:
            continue
        dst = tmp_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel_path == "scripts/demo_paper_workflow.sh":
            shutil.copy2(str(src), str(dst))
            os.chmod(str(dst), 0o755)
        else:
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    original_script = CHECKER_SCRIPT.read_text(encoding="utf-8")
    # Patch module-level paths to point into temp dir
    patched = original_script.replace(
        'REPO_ROOT = Path(__file__).resolve().parent.parent',
        f'REPO_ROOT = Path("{tmp_dir}")'
    )
    tmp_script = tmp_dir / "check_demo_proof.py"
    tmp_script.write_text(patched, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True,
        text=True,
    )
    # Cleanup
    try:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                f.unlink()
        for d in sorted(tmp_dir.rglob("*"), key=lambda p: -len(p.parts)):
            if d.is_dir():
                d.rmdir()
        tmp_dir.rmdir()
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
            f"Demo proof checker failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASSED" in result.stdout


class TestCheckerRejectsForbiddenClaims:
    def test_rejects_live_trading_ready_in_demo_doc(self) -> None:
        original = ARTIFACT_INDEX.read_text(encoding="utf-8")
        injected = original + "\n\nThis project is live trading ready.\n"
        result = _run_checker_with_patched_doc(original, injected, "docs/demo-artifact-index.md")
        assert result.returncode != 0, "Expected failure on forbidden claim injection"
        assert "live trading ready" in result.stdout.lower()

    def test_rejects_guaranteed_profit_in_readme(self) -> None:
        original = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        injected = original + "\n\nThis strategy produces guaranteed profit.\n"
        result = _run_checker_with_patched_doc(original, injected, "README.md")
        assert result.returncode != 0
        assert "guaranteed profit" in result.stdout.lower()


class TestCheckerAcceptsNegativeSafetyWording:
    def test_accepts_not_live_trading_ready(self) -> None:
        original = ARTIFACT_INDEX.read_text(encoding="utf-8")
        injected = original + "\n\nLive trading is not ready.\n"
        result = _run_checker_with_patched_doc(original, injected, "docs/demo-artifact-index.md")
        assert result.returncode == 0, (
            f"Expected pass for negative wording:\n{result.stdout}\n{result.stderr}"
        )


class TestCheckerDetectsMissingSections:
    def test_rejects_missing_safety_scope(self) -> None:
        original = ARTIFACT_INDEX.read_text(encoding="utf-8")
        injected = original.replace("## Safety Scope", "## Safety Boundaries")
        result = _run_checker_with_patched_doc(original, injected, "docs/demo-artifact-index.md")
        assert result.returncode != 0
        assert "safety scope" in result.stdout.lower()

    def test_rejects_missing_success_criteria(self) -> None:
        original = ARTIFACT_INDEX.read_text(encoding="utf-8")
        injected = original.replace("## Success Criteria", "## Completion Criteria")
        result = _run_checker_with_patched_doc(original, injected, "docs/demo-artifact-index.md")
        assert result.returncode != 0
        assert "success criteria" in result.stdout.lower()


class TestCheckerDetectsMissingSafetyClaims:
    def test_rejects_missing_no_live_orders(self) -> None:
        original = ARTIFACT_INDEX.read_text(encoding="utf-8")
        injected = original.replace("No live orders submitted", "No live orders placed")
        result = _run_checker_with_patched_doc(original, injected, "docs/demo-artifact-index.md")
        assert result.returncode != 0
        assert "no live orders submitted" in result.stdout.lower()


class TestCheckerDetectsMissingArtifacts:
    def test_rejects_missing_config_toml(self) -> None:
        original = ARTIFACT_INDEX.read_text(encoding="utf-8")
        injected = original.replace(".atlas/config.toml", ".atlas/settings.toml")
        result = _run_checker_with_patched_doc(original, injected, "docs/demo-artifact-index.md")
        assert result.returncode != 0
        assert "config.toml" in result.stdout.lower()


class TestCheckerDetectsMissingCrossLinks:
    def test_rejects_missing_index_link_in_readme(self) -> None:
        original = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        injected = original.replace("demo-artifact-index.md", "demo-artifact-guide.md")
        result = _run_checker_with_patched_doc(original, injected, "README.md")
        assert result.returncode != 0
        assert "artifact index" in result.stdout.lower()


class TestCheckerDetectsCanonicalReviewerPathIssues:
    def test_rejects_missing_golden_path_link_in_readme(self) -> None:
        original = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        injected = original.replace("reviewer-golden-path.md", "reviewer-guide.md")
        result = _run_checker_with_patched_doc(original, injected, "README.md")
        assert result.returncode != 0
        assert "reviewer-golden-path" in result.stdout.lower()

    def test_rejects_missing_proof_checker_link_in_walkthrough(self) -> None:
        original = (REPO_ROOT / "docs/external-reviewer-walkthrough.md").read_text(encoding="utf-8")
        injected = original.replace("check_demo_proof.py", "verify_demo.py")
        result = _run_checker_with_patched_doc(original, injected, "docs/external-reviewer-walkthrough.md")
        assert result.returncode != 0
        assert "check_demo_proof" in result.stdout.lower()


class TestCheckerDetectsSymbolInconsistency:
    def test_rejects_readme_using_demo_symbol_for_config(self) -> None:
        original = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        injected = original.replace("atlas config set market.symbol ATLAS-DEMO", "atlas config set market.symbol DEMO-SYMBOL")
        result = _run_checker_with_patched_doc(original, injected, "README.md")
        assert result.returncode != 0
        assert "atlas-demo" in result.stdout.lower()


class TestCheckerDetectsStaleOverPromiseClaims:
    def test_rejects_stale_source_version_prepared_claim(self) -> None:
        original = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        injected = original + "\nThe 0.6.8 source version on main is prepared.\n"
        result = _run_checker_with_patched_doc(original, injected, "README.md")
        assert result.returncode != 0
        assert "stale" in result.stdout.lower()

    def test_rejects_production_ready_in_brokers_doc(self) -> None:
        original = (REPO_ROOT / "docs/brokers.md").read_text(encoding="utf-8")
        injected = original.replace("fully implemented", "production-ready")
        result = _run_checker_with_patched_doc(original, injected, "docs/brokers.md")
        assert result.returncode != 0
        assert "production-ready" in result.stdout.lower()


class TestCheckerDoesNotExecuteDemo:
    def test_no_subprocess_call_to_demo_script(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        # The checker should not execute the demo script via subprocess/os.system
        assert "os.system" not in text
        assert "subprocess.call" not in text
        assert "subprocess.run" not in text
        assert "Popen" not in text
        # It may reference the script path as a constant for read-only inspection
        assert "read_text" in text or "_read" in text

    def test_no_network_calls(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        # Forbid actual network imports/calls; allow "curl" as a forbidden-phrase literal
        assert "import requests" not in text
        assert "import urllib" not in text
        assert "import httpx" not in text
        assert "import socket" not in text
        assert "from requests" not in text
        assert "from urllib" not in text
        assert "from httpx" not in text

    def test_no_credential_loading(self) -> None:
        text = CHECKER_SCRIPT.read_text(encoding="utf-8")
        # Forbid credential loading patterns; allow "env" as a forbidden-phrase literal
        assert "load_dotenv" not in text
        assert "getenv(" not in text
        assert "os.environ" not in text
        assert "environ[" not in text


class TestCheckerValidatesCandidateTracking:
    def test_cand_001_implemented_in_json(self) -> None:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        candidates = {c["id"]: c for c in data.get("candidates", [])}
        assert candidates["CAND-001"].get("implemented") is True

    def test_cand_002_implemented_in_json(self) -> None:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        candidates = {c["id"]: c for c in data.get("candidates", [])}
        assert candidates["CAND-002"].get("implemented") is True

    def test_cand_003_implemented_in_json(self) -> None:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        candidates = {c["id"]: c for c in data.get("candidates", [])}
        assert candidates["CAND-003"].get("implemented") is True

    def test_cand_004_implemented_in_json(self) -> None:
        data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        candidates = {c["id"]: c for c in data.get("candidates", [])}
        assert candidates["CAND-004"].get("implemented") is True

    def test_checker_function_detects_bad_json_state(self) -> None:
        mod = _load_checker_module()
        bad_data = {
            "candidates": [
                {"id": "CAND-001", "implemented": False},
                {"id": "CAND-002", "implemented": False},
                {"id": "CAND-003", "implemented": False},
            ]
        }
        violations = mod._check_candidates_json_state(bad_data)
        assert any("CAND-001" in v for v in violations)
        assert any("CAND-002" in v for v in violations)
        assert any("CAND-003" in v for v in violations)

    def test_checker_function_detects_bad_md_state(self) -> None:
        mod = _load_checker_module()
        bad_md = "## Accepted Candidates\n- CAND-001 — not yet implemented\n- CAND-002 — not yet implemented\n- CAND-003 — not yet implemented\n"
        violations = mod._check_candidates_md_state(bad_md)
        assert any("CAND-001" in v and "should be marked implemented" in v for v in violations)
        assert any("CAND-002" in v and "should be marked implemented" in v for v in violations)
        assert any("CAND-003" in v and "should be marked implemented" in v for v in violations)


class TestCheckerUnitFunctions:
    def test_script_shebang_check(self) -> None:
        mod = _load_checker_module()
        assert mod._check_script_shebang_and_flags("#!/usr/bin/env bash\nset -euo pipefail\n") == []
        assert mod._check_script_shebang_and_flags("bad") == ["Demo script missing safe shebang or set flags"]

    def test_script_forbidden_phrases(self) -> None:
        mod = _load_checker_module()
        assert mod._check_script_forbidden_phrases("safe text") == []
        assert mod._check_script_forbidden_phrases("curl https://example.com") != []

    def test_index_sections(self) -> None:
        mod = _load_checker_module()
        assert mod._check_index_required_sections("## Purpose\n## Safety Scope\n") != []
        assert mod._check_index_required_sections("\n".join(mod.REQUIRED_INDEX_SECTIONS)) == []

    def test_index_safety_claims(self) -> None:
        mod = _load_checker_module()
        assert mod._check_index_safety_claims("No live broker credentials required\n") != []
        assert mod._check_index_safety_claims("\n".join(mod.REQUIRED_SAFETY_CLAIMS)) == []

    def test_forbidden_claims_with_negative_context(self) -> None:
        mod = _load_checker_module()
        # This tests the sentence-extraction logic indirectly via the module's constants
        assert "not " in mod.NEGATIVE_CONTEXT_INDICATORS

    def test_symbol_consistency_passes(self) -> None:
        mod = _load_checker_module()
        # With the real repo files, this should pass
        violations = mod._check_symbol_consistency()
        assert violations == []

    def test_canonical_reviewer_path_passes(self) -> None:
        mod = _load_checker_module()
        violations = mod._check_canonical_reviewer_path()
        assert violations == []

    def test_stale_over_promise_passes(self) -> None:
        mod = _load_checker_module()
        violations = mod._check_stale_over_promise_claims()
        assert violations == []
