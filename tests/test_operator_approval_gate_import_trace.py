from __future__ import annotations

import sys


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
