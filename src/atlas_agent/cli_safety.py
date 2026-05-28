from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.safety import KillSwitchController


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
    enabled = config.kill_switch_enabled or _kill_switch_controller(config).is_enabled()
    if enabled == config.kill_switch_enabled:
        return config
    return config.model_copy(
        update={"safety": config.safety.model_copy(update={"kill_switch_enabled": enabled})}
    )
