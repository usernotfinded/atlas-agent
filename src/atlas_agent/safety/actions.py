from __future__ import annotations

from typing import Literal

SafetyActionType = Literal[
    "cancel_order",
    "cancel_all_orders",
    "flatten_position",
    "flatten_all_positions",
    "notify_user",
    "request_user_approval",
    "no_op"
]
