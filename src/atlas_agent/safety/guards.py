from __future__ import annotations

from atlas_agent.config import AtlasConfig


def live_mode_guard(config: AtlasConfig) -> tuple[bool, tuple[str, ...]]:
    reasons = config.live_disabled_reasons()
    return (not reasons, reasons)

