from __future__ import annotations

import json
from pathlib import Path
from atlas_agent.cli import main


def test_dashboard_command_generates_html(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Init a workspace
    assert main(["init", ".", "--force"]) == 0
    
    # Generate dashboard
    assert main(["dashboard"]) == 0
    
    dashboard_path = tmp_path / ".atlas" / "dashboard" / "index.html"
    assert dashboard_path.exists()
    assert "Atlas Agent" in dashboard_path.read_text()


def test_dashboard_json_flag_emits_valid_json(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--force"]) == 0
    capsys.readouterr() # Clear buffer
    
    assert main(["dashboard", "--json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    
    assert data["workspace"] == str(tmp_path)
    assert data["configured"] is True
