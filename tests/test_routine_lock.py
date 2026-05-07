from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from atlas_agent.config import AtlasConfig
from atlas_agent.research.web_research import OfflineResearchProvider
from atlas_agent.routines.engine import run_routine
from atlas_agent.routines.lock import (
    RoutineLockError,
    acquire_routine_lock,
    lock_path,
    unlock_routine,
)


def _config(tmp_path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
    )


def test_second_routine_run_refuses_while_lock_exists(tmp_path) -> None:
    lock = acquire_routine_lock(tmp_path, "pre_market")
    try:
        with pytest.raises(RoutineLockError, match="routine lock is active"):
            run_routine(
                "pre_market",
                mode="paper",
                config=_config(tmp_path),
                research_provider=OfflineResearchProvider(),
            )
    finally:
        lock.release()


def test_stale_lock_can_be_cleared(tmp_path) -> None:
    path = lock_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "routine": "pre_market",
                "pid": os.getpid(),
                "timestamp": (datetime.now(UTC) - timedelta(hours=7)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    message = unlock_routine(tmp_path)

    assert "removed stale routine lock" in message
    assert not path.exists()


def test_lock_is_released_after_successful_run(tmp_path) -> None:
    result = run_routine(
        "pre_market",
        mode="paper",
        config=_config(tmp_path),
        research_provider=OfflineResearchProvider(),
    )

    assert result.status == "complete"
    assert not lock_path(tmp_path).exists()

