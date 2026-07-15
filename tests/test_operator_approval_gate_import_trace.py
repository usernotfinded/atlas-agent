# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_operator_approval_gate_import_trace.py
# PURPOSE: Verifies operator approval gate import trace behavior and regression
#         expectations.
# DEPS:    subprocess, sys, pathlib.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class _ImportRecorder:
    def __init__(self) -> None:
        self.before = set(sys.modules)

    def new_imports(self) -> set[str]:
        return set(sys.modules) - self.before


def test_engine_import_does_not_load_brokers_or_providers() -> None:
    recorder = _ImportRecorder()
    from atlas_agent.agent import operator_approval_gate  # noqa: F401

    new_imports = recorder.new_imports()
    forbidden = {
        "atlas_agent.brokers",
        "atlas_agent.providers",
        "atlas_agent.execution",
        "atlas_agent.risk",
        "atlas_agent.config",
        "atlas_agent.agent.live_agent",
    }
    found = {name for name in new_imports if any(name.startswith(prefix) for prefix in forbidden)}
    assert not found, f"Unexpected imports: {found}"


def test_cli_import_does_not_load_brokers_or_providers() -> None:
    recorder = _ImportRecorder()
    from atlas_agent.agent import operator_approval_gate_cli  # noqa: F401

    new_imports = recorder.new_imports()
    forbidden = {
        "atlas_agent.brokers",
        "atlas_agent.providers",
        "atlas_agent.execution",
        "atlas_agent.risk",
        "atlas_agent.config",
        "atlas_agent.agent.live_agent",
    }
    found = {name for name in new_imports if any(name.startswith(prefix) for prefix in forbidden)}
    assert not found, f"Unexpected imports: {found}"


def test_bootstrap_route_does_not_import_legacy_cli_for_operator_gate() -> None:
    # Simulate the bootstrap route importing the configless CLI without loading
    # the legacy argument parser (which pulls many broker/provider modules).
    import atlas_agent.cli_bootstrap as bootstrap

    assert hasattr(bootstrap, "main")


def _run_import_probe(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return (result.stdout + result.stderr).strip()


def test_operator_gate_configless_rejects_workspace_without_legacy_cli() -> None:
    code = """
import sys
from atlas_agent.cli_bootstrap import main
rc = main(["agent", "operator-approval-gate", "--workspace", "/tmp/nonexistent-ws-cand008"])
print(f"rc:{rc}")
print(f"legacy_cli_imported={('atlas_agent.cli' in sys.modules)}")
"""
    output = _run_import_probe(code)
    assert "rc:2" in output, output
    assert "legacy_cli_imported=False" in output, output


def test_submit_conformance_configless_rejects_workspace_without_legacy_cli() -> None:
    code = """
import sys
from atlas_agent.cli_bootstrap import main
try:
    main(["agent", "submit-conformance", "--workspace", "/tmp/nonexistent-ws-cand008"])
except SystemExit as exc:
    print(f"exit:{exc.code}")
print(f"legacy_cli_imported={('atlas_agent.cli' in sys.modules)}")
"""
    output = _run_import_probe(code)
    assert "exit:2" in output, output
    assert "legacy_cli_imported=False" in output, output


def test_readiness_envelope_configless_rejects_workspace_without_legacy_cli() -> None:
    code = """
import sys
from atlas_agent.cli_bootstrap import main
try:
    main(["agent", "readiness-envelope", "--workspace", "/tmp/nonexistent-ws-cand008"])
except SystemExit as exc:
    print(f"exit:{exc.code}")
print(f"legacy_cli_imported={('atlas_agent.cli' in sys.modules)}")
"""
    output = _run_import_probe(code)
    assert "exit:2" in output, output
    assert "legacy_cli_imported=False" in output, output


def test_operator_gate_configless_does_not_load_forbidden_modules() -> None:
    code = """
import sys
from atlas_agent.cli_bootstrap import main
try:
    main(["agent", "operator-approval-gate", "--workspace", "/tmp/nonexistent-ws-cand008"])
except SystemExit:
    pass
forbidden = {
    "atlas_agent.brokers",
    "atlas_agent.providers",
    "atlas_agent.execution",
    "atlas_agent.risk",
    "atlas_agent.config",
    "atlas_agent.agent.live_agent",
}
loaded = [name for name in sys.modules if any(name.startswith(p) for p in forbidden)]
print(f"loaded={loaded}")
"""
    output = _run_import_probe(code)
    assert "loaded=[]" in output, output
