from __future__ import annotations

import logging
from pathlib import Path
from datetime import UTC, datetime

from atlas_agent.safety.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)


class HeartbeatManager:
    def __init__(self, heartbeat_path: str | Path, timeout_seconds: int = 300):
        self.heartbeat_path = Path(heartbeat_path)
        self.timeout_seconds = timeout_seconds

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

    def is_expired(self) -> bool:
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
