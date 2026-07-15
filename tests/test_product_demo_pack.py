# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_product_demo_pack.py
# PURPOSE: Verifies product demo pack behavior and regression expectations.
# DEPS:    json, os, shutil, subprocess, sys, tempfile, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DEMO_DOC = ROOT / "docs" / "product-demo-pack.md"
MARKETPLACE_DOC = ROOT / "docs" / "marketplace-listing.md"
AUTONOMY_DOC = ROOT / "docs" / "autonomy-roadmap.md"
DEMO_SCRIPT = ROOT / "scripts" / "demo_product_walkthrough.sh"
CHECKER_SCRIPT = ROOT / "scripts" / "check_product_demo_pack.py"
README = ROOT / "README.md"

FORBIDDEN_MARKETPLACE_PHRASES = [
    "live trading ready",
    "production trading ready",
    "real-money ready",
    "autonomous trading ready",
    "fully autonomous",
    "safe live trading",
    "guaranteed profit",
    "guaranteed returns",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "zero risk",
    "risk-free",
    "no risk",
    "passive income",
]

REQUIRED_DOC_PHRASES = {
    PRODUCT_DEMO_DOC: [
        "Not financial advice",
        "paper-only",
        "no credentials",
        "no live trading",
        "scripts/demo_product_walkthrough.sh",
        "scripts/check_product_demo_pack.py",
    ],
    MARKETPLACE_DOC: [
        "Not financial advice",
        "Live trading is disabled by default",
        "paper-first",
        "broker-neutral",
        "not autonomous",
        "not a live-trading-ready product",
    ],
    AUTONOMY_DOC: [
        "Not financial advice",
        "supervised, not autonomous",
        "No promise of profitability",
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "out of scope",
    ],
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.mark.parametrize("path", [PRODUCT_DEMO_DOC, MARKETPLACE_DOC, AUTONOMY_DOC])
def test_required_doc_exists(path: Path) -> None:
    assert path.exists(), f"Required doc missing: {path}"


def test_demo_script_exists_and_is_executable() -> None:
    assert DEMO_SCRIPT.exists(), "Demo script missing"
    assert DEMO_SCRIPT.is_file(), "Demo script is not a file"
    assert os.access(DEMO_SCRIPT, os.X_OK), "Demo script is not executable"


def test_checker_script_exists_and_is_executable() -> None:
    assert CHECKER_SCRIPT.exists(), "Checker script missing"
    assert CHECKER_SCRIPT.is_file(), "Checker script is not a file"
    assert os.access(CHECKER_SCRIPT, os.X_OK), "Checker script is not executable"


def test_demo_script_has_safe_shebang_and_flags() -> None:
    text = DEMO_SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"), (
        "Demo script missing safe shebang or set flags"
    )


def test_demo_script_uses_paper_mode_and_dry_run() -> None:
    text = DEMO_SCRIPT.read_text(encoding="utf-8")
    assert "run --mode paper --dry-run" in text
    assert "--mode live" not in text


def test_demo_script_does_not_use_network_or_credentials() -> None:
    text = DEMO_SCRIPT.read_text(encoding="utf-8").lower()
    forbidden = [
        "curl ",
        "wget ",
        "api_key",
        "secret_key",
        "bearer ",
    ]
    for phrase in forbidden:
        assert phrase not in text, f"Demo script contains unsafe pattern: {phrase}"


@pytest.mark.parametrize("path,phrases", REQUIRED_DOC_PHRASES.items())
def test_required_phrases_present(path: Path, phrases: list[str]) -> None:
    text = path.read_text(encoding="utf-8").lower()
    for phrase in phrases:
        assert phrase.lower() in text, f"[{path.name}] Missing required phrase: {phrase}"


@pytest.mark.parametrize("phrase", FORBIDDEN_MARKETPLACE_PHRASES)
def test_marketplace_doc_forbids_unsafe_claims(phrase: str) -> None:
    text = MARKETPLACE_DOC.read_text(encoding="utf-8").lower()
    # Allow the phrase only inside a clearly negative/disclaimer context.
    if phrase in text:
        negative_indicators = (
            "not ",
            "does not",
            "never",
            "no ",
            "not a ",
            "out of scope",
        )
        for line in text.splitlines():
            if phrase in line:
                assert any(ind in line for ind in negative_indicators), (
                    f"Forbidden phrase '{phrase}' appears without negative context: {line}"
                )


def test_autonomy_roadmap_distinguishes_current_and_future() -> None:
    text = AUTONOMY_DOC.read_text(encoding="utf-8").lower()
    assert "current state" in text
    assert any(
        marker in text
        for marker in [
            "not implemented in the current release",
            "out of scope",
            "not a project goal",
        ]
    )


def test_product_demo_pack_links_to_new_files() -> None:
    text = PRODUCT_DEMO_DOC.read_text(encoding="utf-8")
    for link in [
        "marketplace-listing.md",
        "autonomy-roadmap.md",
        "demo_product_walkthrough.sh",
        "check_product_demo_pack.py",
    ]:
        assert link in text, f"product-demo-pack.md missing link to {link}"


def test_readme_links_to_product_demo_pack() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docs/product-demo-pack.md" in text
    assert "scripts/demo_product_walkthrough.sh" in text


def test_checker_script_runs_and_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Checker failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "PASSED" in result.stdout


def test_checker_script_json_output() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["files_checked"] >= 7
    assert "summary" in data
    assert "PASSED" in data["summary"]
    assert isinstance(data["errors"], list)
    assert isinstance(data["warnings"], list)


def test_demo_script_help_and_rejects_unknown_options() -> None:
    help_result = subprocess.run(
        [str(DEMO_SCRIPT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "Usage:" in help_result.stdout

    bad_result = subprocess.run(
        [str(DEMO_SCRIPT), "--not-a-real-option"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert bad_result.returncode != 0, "Unknown option should be rejected"
    assert "Unknown option" in bad_result.stderr


def test_checker_detects_injected_forbidden_phrase() -> None:
    """Copy the pack into a temp tree, inject an unsafe claim, and verify the checker fails."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        tmp_docs = tmp_root / "docs"
        tmp_scripts = tmp_root / "scripts"
        tmp_tests = tmp_root / "tests"
        tmp_docs.mkdir()
        tmp_scripts.mkdir()
        tmp_tests.mkdir()

        shutil.copy(PRODUCT_DEMO_DOC, tmp_docs / "product-demo-pack.md")
        shutil.copy(MARKETPLACE_DOC, tmp_docs / "marketplace-listing.md")
        shutil.copy(AUTONOMY_DOC, tmp_docs / "autonomy-roadmap.md")
        shutil.copy(DEMO_SCRIPT, tmp_scripts / "demo_product_walkthrough.sh")
        shutil.copy(CHECKER_SCRIPT, tmp_scripts / "check_product_demo_pack.py")
        shutil.copy(Path(__file__), tmp_tests / "test_product_demo_pack.py")

        # Inject a forbidden marketing claim into the marketplace listing copy.
        bad_marketplace = (tmp_docs / "marketplace-listing.md").read_text(encoding="utf-8")
        bad_marketplace += "\nAtlas is guaranteed to beat the market.\n"
        (tmp_docs / "marketplace-listing.md").write_text(bad_marketplace, encoding="utf-8")

        # Make the demo script executable so the checker is happy with everything else.
        os.chmod(tmp_scripts / "demo_product_walkthrough.sh", 0o755)
        os.chmod(tmp_scripts / "check_product_demo_pack.py", 0o755)

        result = subprocess.run(
            [sys.executable, str(tmp_scripts / "check_product_demo_pack.py"), "--json"],
            cwd=tmp_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Checker should fail on injected forbidden phrase. stdout:\n{result.stdout}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any(
            "guaranteed" in err.lower() or "beat the market" in err.lower()
            for err in data["errors"]
        ), data["errors"]
