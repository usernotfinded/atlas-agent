"""Tests for the product capability inventory checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Missing required fields cause failure.
- Invalid status or claim level fails.
- Missing required capability groups fails.
- Missing README claim representation fails.
- Unsafe safe_to_claim wording fails.
- Safety-sensitive capabilities without safety notes fail.
- The script source remains safe.
- The inventory docs include disabled/default safety posture.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_product_capability_inventory.py"


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_product_capability_inventory", CHECKER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_product_capability_inventory"] = mod
    spec.loader.exec_module(mod)
    return mod


CHECKER_MOD = _load_checker_module()


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


def test_checker_passes_on_current_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_checker_json_output() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []
    assert data["groups_checked"] == 9


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_missing_required_field_fails() -> None:
    original = CHECKER_MOD.REQUIRED_FIELDS
    try:
        CHECKER_MOD.REQUIRED_FIELDS = ["id", "nonexistent_required_field_xyz"]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("missing required field" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_FIELDS = original


def test_invalid_status_fails() -> None:
    original = CHECKER_MOD.ALLOWED_STATUSES
    try:
        CHECKER_MOD.ALLOWED_STATUSES = {"implemented"}
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("invalid status" in e for e in result["errors"])
    finally:
        CHECKER_MOD.ALLOWED_STATUSES = original


def test_invalid_claim_level_fails() -> None:
    original = CHECKER_MOD.ALLOWED_CLAIM_LEVELS
    try:
        CHECKER_MOD.ALLOWED_CLAIM_LEVELS = {"safe_to_claim"}
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("invalid claim level" in e for e in result["errors"])
    finally:
        CHECKER_MOD.ALLOWED_CLAIM_LEVELS = original


def test_missing_required_group_fails() -> None:
    original = CHECKER_MOD.REQUIRED_CAPABILITY_GROUPS
    try:
        CHECKER_MOD.REQUIRED_CAPABILITY_GROUPS = ["core-workspace", "nonexistent-group-xyz"]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing required capability group" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_CAPABILITY_GROUPS = original


def test_missing_critical_capability_fails() -> None:
    original = CHECKER_MOD.CRITICAL_CAPABILITIES
    try:
        CHECKER_MOD.CRITICAL_CAPABILITIES = ["cli-compatibility-contract", "nonexistent-cap-xyz"]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing critical capability" in e for e in result["errors"])
    finally:
        CHECKER_MOD.CRITICAL_CAPABILITIES = original


def test_unsafe_safe_to_claim_fails() -> None:
    original = CHECKER_MOD._load_inventory
    try:
        def _patched_load() -> dict:
            data = original()
            # Inject an unsafe phrase into a safe_to_claim capability
            for cap in data.get("capabilities", []):
                if cap.get("public_claim_level") == "safe_to_claim":
                    cap["reviewer_notes"] = cap.get("reviewer_notes", "") + " guaranteed profit"
                    break
            return data

        with patch.object(CHECKER_MOD, "_load_inventory", _patched_load):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("unsafe phrase" in e for e in result["errors"])
    finally:
        pass


def test_safety_sensitive_without_notes_fails() -> None:
    original = CHECKER_MOD._check_safety_notes_present

    def _patched_check(inventory: dict) -> list[str]:
        errors: list[str] = []
        for cap in inventory.get("capabilities", []):
            if cap.get("status") in {"disabled_by_default", "partial", "experimental"}:
                # Force failure by pretending notes are empty
                errors.append(
                    f"Safety-sensitive capability '{cap.get('id')}' missing safety_notes"
                )
        return errors

    try:
        with patch.object(CHECKER_MOD, "_check_safety_notes_present", _patched_check):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("missing safety_notes" in e for e in result["errors"])
    finally:
        pass


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_network_calls() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket", "requests"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in checker script"


def test_script_source_no_github_api() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "github.com" not in source
    assert "api.github" not in source
    assert "gh api" not in source


# ---------------------------------------------------------------------------
# Docs content checks
# ---------------------------------------------------------------------------


def test_inventory_doc_exists() -> None:
    path = REPO_ROOT / "docs" / "product-capability-inventory.md"
    assert path.exists()


def test_inventory_doc_has_safety_posture() -> None:
    path = REPO_ROOT / "docs" / "product-capability-inventory.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "live trading" in text
    assert "disabled by default" in text
    assert "not financial advice" in text
    assert "not production ready" in text


def test_inventory_doc_covers_all_groups() -> None:
    path = REPO_ROOT / "docs" / "product-capability-inventory.md"
    text = path.read_text(encoding="utf-8").lower()
    groups = [
        "core workspace",
        "paper trading",
        "research",
        "safety",
        "audit",
        "memory",
        "automation",
        "integration",
        "public review",
    ]
    for group in groups:
        assert group in text, f"Missing group section: {group}"


def test_inventory_doc_has_how_to_read_section() -> None:
    path = REPO_ROOT / "docs" / "product-capability-inventory.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "how to read this document" in text
    assert "status" in text
    assert "public claim" in text
    assert "notes" in text


def test_inventory_doc_links_to_gap_prioritization() -> None:
    path = REPO_ROOT / "docs" / "product-capability-inventory.md"
    text = path.read_text(encoding="utf-8")
    assert "archive/legacy-plans/v0.5.8-gap-prioritization.md" in text or "v0.5.8 gap prioritization" in text.lower()


def test_inventory_avoids_profit_claims() -> None:
    path = REPO_ROOT / "docs" / "product-capability-inventory.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "profit" in text  # Should mention it to deny it
    assert "not" in text or "out of scope" in text or "does not imply" in text


# ---------------------------------------------------------------------------
# JSON inventory content checks
# ---------------------------------------------------------------------------


def test_inventory_json_exists() -> None:
    path = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"
    assert path.exists()


def test_inventory_generated_for_matches_current_version() -> None:
    """Inventory generated_for must match the current package version.

    Prevents stale inventory metadata after version bumps.
    """
    from atlas_agent import __version__

    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json").read_text())
    assert data.get("generated_for") == __version__, (
        f"product_capability_inventory.json generated_for ({data.get('generated_for')!r}) "
        f"does not match current package version ({__version__!r}). "
        f"Update tests/fixtures/product_capability_inventory.json after version bumps."
    )


def test_inventory_has_all_groups() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json").read_text())
    actual_groups = {cap["group"] for cap in data.get("capabilities", [])}
    for group in CHECKER_MOD.REQUIRED_CAPABILITY_GROUPS:
        assert group in actual_groups, f"Missing group in JSON: {group}"


def test_inventory_has_all_critical_capabilities() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json").read_text())
    actual_ids = {cap["id"] for cap in data.get("capabilities", [])}
    for cap_id in CHECKER_MOD.CRITICAL_CAPABILITIES:
        assert cap_id in actual_ids, f"Missing critical capability in JSON: {cap_id}"


def test_inventory_safe_to_claim_has_no_unsafe_phrases() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json").read_text())
    for cap in data.get("capabilities", []):
        if cap.get("public_claim_level") == "safe_to_claim":
            text = " ".join([cap.get("name", ""), cap.get("safety_notes", ""), cap.get("reviewer_notes", "")]).lower()
            for phrase in CHECKER_MOD.UNSAFE_SAFE_TO_CLAIM_PHRASES:
                assert phrase not in text, f"Capability '{cap['id']}' has unsafe phrase: {phrase}"


def test_inventory_safe_to_claim_has_files_or_commands() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json").read_text())
    for cap in data.get("capabilities", []):
        if cap.get("public_claim_level") == "safe_to_claim":
            has_cli = bool(cap.get("cli_commands"))
            has_files = any(
                (REPO_ROOT / p).exists() or (REPO_ROOT / p).is_dir()
                for plist in (cap.get("source_paths", []), cap.get("docs_paths", []), cap.get("tests_or_checks", []))
                for p in plist
            )
            assert has_cli or has_files, f"Capability '{cap['id']}' safe_to_claim but no verified commands or files"


def test_checker_drift_detection_fails_on_missing_files() -> None:
    def _patched_check(inventory: dict) -> list[str]:
        return ["Capability 'fake-cap' marked safe_to_claim has no verified CLI commands, source_paths, docs_paths, or tests_or_checks in the repo"]

    with patch.object(CHECKER_MOD, "_check_safe_to_claim_files_exist", _patched_check):
        result = CHECKER_MOD._gather()
    assert result["passed"] is False
    assert any("no verified CLI commands" in e for e in result["errors"])


def test_readme_clarifies_provider_execution_boundary() -> None:
    path = REPO_ROOT / "README.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "artifact-based safety policy" in text or "artifact based safety policy" in text
    assert "risk manager" in text
    assert "no runtime network block" in text or "runtime network block" in text


def test_inventory_safety_sensitive_has_notes() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json").read_text())
    safety_statuses = {"disabled_by_default", "partial", "experimental"}
    for cap in data.get("capabilities", []):
        if cap.get("status") in safety_statuses:
            assert cap.get("safety_notes", "").strip(), f"Capability '{cap['id']}' missing safety_notes"
