# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/models.py
# PURPOSE: The vocabulary of the safety domain: the kill switch modes, the verdicts
#          they produce, and the shape of the action plans that carry them out.
# DEPS:    pydantic (models), safety.actions (action type enum)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Any, Literal, Optional, List
from pydantic import BaseModel, Field


# ==============================================================================
# KILL SWITCH
# ==============================================================================

# Ordered by severity, and the order matters — each mode is a superset of the
# restrictions of the one before it:
#   normal      → trade freely
#   soft_pause  → stop opening; leave what is open alone
#   cancel_all  → also pull resting orders
#   flatten_all → also close existing positions (the only mode that TRADES to exit)
#   locked_down → touch nothing at all; the terminal state a corrupt file falls into
KillSwitchMode = Literal[
    "normal",
    "soft_pause",
    "cancel_all",
    "flatten_all",
    "locked_down"
]


class KillSwitchStatus(BaseModel):
    # Defaults describe an untripped switch, so an absent state file deserialises
    # into exactly this — see KillSwitchState.load().
    mode: KillSwitchMode = "normal"
    reason: str = "System default"
    updated_at: str = ""
    actor: str = "system"


class KillSwitchDecision(BaseModel):
    # `allowed` is the answer to "may this order proceed?"; `status` says *why*, and
    # `action_required` says what the system owes the operator in response (cancel,
    # flatten). Callers must not infer any of the three from the others.
    allowed: bool
    status: Literal["allowed", "blocked", "cancel_required", "flatten_required", "locked_down"]
    reason: Optional[str] = None
    mode: KillSwitchMode
    action_required: Optional[str] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


# Imported here rather than at the top to keep the import graph acyclic: actions.py
# is a leaf that this module builds on, and hoisting it would invite the reverse edge.
from atlas_agent.safety.actions import SafetyActionType


# ==============================================================================
# SAFETY ACTION PLANS
# ==============================================================================

class SafetyAction(BaseModel):
    type: SafetyActionType
    description: str
    params: dict[str, Any] = Field(default_factory=dict)


class SafetyActionPlan(BaseModel):
    plan_id: str
    mode: KillSwitchMode
    status: Literal["planned", "blocked", "requires_approval", "completed", "failed"]
    reason: str
    actions: List[SafetyAction] = Field(default_factory=list)

    # Defaults to True. A safety plan can place real orders (flatten_all sells), so
    # the burden is on the caller to declare it pre-authorised — never on this model
    # to assume it.
    requires_approval: bool = True
    diagnostics: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# EXECUTION RESULTS
# ==============================================================================

# "partially_completed" is not a rounding of success: a flatten that closed two of
# three positions leaves real exposure open, and the caller has to be able to see
# that rather than read a green "completed".
SafetyActionExecutionStatus = Literal[
    "skipped",
    "requires_approval",
    "completed",
    "partially_completed",
    "failed",
    "blocked"
]


class SafetyActionExecutionResult(BaseModel):
    action_type: SafetyActionType
    status: SafetyActionExecutionStatus
    tool_name: Optional[str] = None
    tool_result: Optional[Any] = None
    error: Optional[str] = None
    simulated: bool = False


class SafetyPlanExecutionResult(BaseModel):
    plan_id: str
    status: SafetyActionExecutionStatus
    executed_actions: List[SafetyActionExecutionResult] = Field(default_factory=list)
    skipped_actions: List[SafetyAction] = Field(default_factory=list)
    failed_actions: List[SafetyActionExecutionResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
