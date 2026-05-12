import json
from pathlib import Path
import pytest

@pytest.fixture
def write_complete_setup_config():
    def _write(workspace: Path, provider="anthropic", model="claude-opus-4-7"):
        atlas_dir = workspace / ".atlas"
        atlas_dir.mkdir(parents=True, exist_ok=True)
        config_file = atlas_dir / "config.json"
        config_data = {
            "setup_mode": "quick",
            "provider": provider,
            "model": model,
            "messaging": "cli",
            "workspace_path": str(workspace),
            "trust_mode": "paper",
            "broker_mode": "paper",
            "update_channel": "stable",
            "credentials_configured": True
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        # Also satisfy credential requirement
        env_atlas = workspace / ".env.atlas"
        env_atlas.write_text(f"ANTHROPIC_API_KEY=test-key\n", encoding="utf-8")
        return config_data
    return _write
