# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_safety.py
# PURPOSE: Wires the kill switch into the CLI. Reconciles the *declared* config
#          with the switch's on-disk runtime state before any command acts on it.
# DEPS:    atlas_agent.config (AtlasConfig), atlas_agent.safety (KillSwitchController),
#          atlas_agent.execution.audit (decision trail)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.safety import KillSwitchController


# ==============================================================================
# KILL SWITCH WIRING
# ==============================================================================

def _kill_switch_controller(config: AtlasConfig) -> KillSwitchController:
    audit_logger = AuditLogger(config.audit_dir)

    def _audit_hook(event_type: str, actor: str, payload: dict[str, Any]) -> None:
        record = dict(payload)
        record["actor"] = actor
        audit_logger.write(event_type, record)

    return KillSwitchController(
        state_path=config.memory_dir / "kill_switch_state.json",
        enabled_flag_path=config.memory_dir / "kill_switch.enabled",
        audit_hook=_audit_hook,
    )


def _effective_config_with_runtime_kill_switch(config: AtlasConfig) -> AtlasConfig:
    # OR, never AND: the switch is armed if *either* the config says so or the
    # on-disk runtime flag says so. A tripped kill switch has to survive a config
    # reload, otherwise editing the YAML would silently disarm it.
    enabled = config.kill_switch_enabled or _kill_switch_controller(config).is_enabled()
    if enabled == config.kill_switch_enabled:
        return config
    # model_copy rather than mutation: AtlasConfig is shared across handlers, and a
    # command must not be able to disarm the switch for the ones that follow it.
    return config.model_copy(
        update={"safety": config.safety.model_copy(update={"kill_switch_enabled": enabled})}
    )
