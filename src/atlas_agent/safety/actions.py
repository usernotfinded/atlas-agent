# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/actions.py
# PURPOSE: The closed set of actions a safety plan may contain. Kept in its own
#          leaf module so both models.py and the executor can depend on it without
#          creating an import cycle.
# DEPS:    stdlib only (typing)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from typing import Literal


# --- CONFIGURATIONS & CONSTANTS ---

# Exhaustive by design: the safety executor dispatches on this Literal, so an action
# that is not named here simply cannot be executed. That is the guarantee — the kill
# switch can never be talked into doing something outside this list.
SafetyActionType = Literal[
    "cancel_order",
    "cancel_all_orders",
    "flatten_position",
    "flatten_all_positions",
    "notify_user",
    "request_user_approval",
    "no_op"
]
