# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/__init__.py
# PURPOSE: Public surface of the safety domain — the three independent brakes on
#          the system, exported from one place:
#            - kill switch   → an operator stops the agent (and can flatten);
#            - deadman       → the agent stopping *itself* when it loses liveness;
#            - action plan   → what either of those is allowed to actually do.
# DEPS:    safety.deadman, safety.kill_switch, safety.action_plan, safety.models
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.safety.deadman import (
    DeadmanConfig,
    DeadmanSwitch,
    HeartbeatRecord,
    HeartbeatStatus,
    deadman_heartbeat_path,
    read_deadman_heartbeat,
    write_deadman_heartbeat,
)
from atlas_agent.safety.guards import live_mode_guard
from atlas_agent.safety.kill_switch import (
    KILL_SWITCH_MODES,
    AdvancedKillSwitch,
    KillSwitchController,
    KillSwitchState,
    KillSwitchTransition,
)
from atlas_agent.safety.action_plan import SafetyActionPlanner
from atlas_agent.safety.models import (
    SafetyAction,
    SafetyActionPlan,
    SafetyActionType,
    KillSwitchMode,
    KillSwitchDecision,
)

# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "DeadmanConfig",
    "DeadmanSwitch",
    "HeartbeatRecord",
    "HeartbeatStatus",
    "KILL_SWITCH_MODES",
    "AdvancedKillSwitch",
    "KillSwitchController",
    "KillSwitchState",
    "KillSwitchTransition",
    "SafetyActionPlanner",
    "SafetyAction",
    "SafetyActionPlan",
    "SafetyActionType",
    "KillSwitchMode",
    "KillSwitchDecision",
    "deadman_heartbeat_path",
    "live_mode_guard",
    "read_deadman_heartbeat",
    "write_deadman_heartbeat",
]
