from __future__ import annotations

import json
from pathlib import Path
from atlas_agent.config import AtlasConfig
from atlas_agent.dashboard.collectors import collect_dashboard_snapshot


def test_collect_dashboard_snapshot_handles_empty_workspace(tmp_path: Path):
    config = AtlasConfig(audit_dir=tmp_path / "audit")
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    
    assert snapshot.workspace == str(tmp_path)
    assert snapshot.configured is True
    assert snapshot.provider_summary.status == "missing"
    assert snapshot.broker_sync_summary.status == "unknown"


def test_collect_dashboard_snapshot_redacts_diagnostics(tmp_path: Path):
    config = AtlasConfig()
    snapshot = collect_dashboard_snapshot(config, tmp_path)
    
    assert snapshot.diagnostics.get("redacted") is True
