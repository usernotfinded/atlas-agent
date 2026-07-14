# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/heartbeat.py
# PURPOSE: Liveness signal. A running agent stamps this file; a stale stamp means
#          the agent died with positions open, which is what the deadman switch
#          watches for.
# DEPS:    safety.atomic_write (torn writes here would fake a liveness signal)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import UTC, datetime

from atlas_agent.safety.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)


# ==============================================================================
# HEARTBEAT MANAGER
# ==============================================================================

class HeartbeatManager:
    def __init__(self, heartbeat_path: str | Path, timeout_seconds: int = 300):
        self.heartbeat_path = Path(heartbeat_path)
        self.timeout_seconds = timeout_seconds

    # --- Write side ---

    def record(self, source: str = "agent"):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": source,
        }
        atomic_write_json(
            self.heartbeat_path,
            payload,
            chmod=0o600,
        )

    # --- Read side (fails closed) ---

    def is_expired(self) -> bool:
        # A file that was never written is "fresh", not expired: on a first run there
        # is no agent to have died, and no positions to protect. Reporting expiry here
        # would trip the deadman on every clean install.
        if not self.heartbeat_path.exists():
            return False  # No heartbeat recorded yet is considered fresh for now

        try:
            payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
            last_ts = datetime.fromisoformat(payload["timestamp"])
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=UTC)

            elapsed = (datetime.now(UTC) - last_ts).total_seconds()
            return elapsed > self.timeout_seconds
        except Exception as exc:
            # Fail CLOSED — the asymmetry is the point. A corrupt heartbeat means we
            # cannot prove the agent is alive, and treating "unknown" as "alive" would
            # disarm the deadman precisely when the system is already misbehaving.
            # The cost of being wrong here is a spurious safety trip; the cost of the
            # opposite default is an unsupervised agent holding open positions.
            logger.warning(
                "HeartbeatManager: corrupt heartbeat file (%s: %s). Treating as expired.",
                type(exc).__name__,
                exc,
            )
            return True  # Corrupt heartbeat fails closed

    def last_heartbeat(self) -> datetime | None:
        if not self.heartbeat_path.exists():
            return None
        try:
            payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
            return datetime.fromisoformat(payload["timestamp"])
        except Exception as exc:
            logger.warning(
                "HeartbeatManager: corrupt heartbeat file (%s: %s). Unable to read last heartbeat.",
                type(exc).__name__,
                exc,
            )
            return None
