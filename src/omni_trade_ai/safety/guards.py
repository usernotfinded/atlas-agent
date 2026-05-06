from __future__ import annotations

from omni_trade_ai.config import OmniTradeConfig


def live_mode_guard(config: OmniTradeConfig) -> tuple[bool, tuple[str, ...]]:
    reasons = config.live_disabled_reasons()
    return (not reasons, reasons)

