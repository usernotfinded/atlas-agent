import os
import json
import subprocess
from pathlib import Path
import pytest

def run_cmd(cmd: str, cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def test_manual_smoke_ux_regression(tmp_path, monkeypatch):
    """
    Test the exact sequence from the UX regression bug report:
    atlas config paths
    atlas config show
    atlas config show --effective
    atlas config doctor
    atlas config set model.provider openrouter
    atlas config set model.default openai/gpt-5.5
    atlas config set providers.openrouter.api_key YOUR_API_KEY_HERE
    atlas config show
    atlas config show --effective
    atlas model current
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)

    # 1. atlas config paths
    code, out, err = run_cmd("atlas config paths", cwd=tmp_path)
    assert code == 0
    assert "Config TOML" in out
    assert "Secrets ENV" in out

    # 2. atlas config show
    code, out, err = run_cmd("atlas config show", cwd=tmp_path)
    assert code == 0

    # 3. atlas config show --effective
    code, out, err = run_cmd("atlas config show --effective", cwd=tmp_path)
    assert code == 0
    assert json.loads(out)  # Should be valid JSON now without PosixPath errors

    # 4. atlas config doctor
    code, out, err = run_cmd("atlas config doctor", cwd=tmp_path)
    assert code == 0

    # 5. atlas config set model.provider openrouter
    code, out, err = run_cmd("atlas config set model.provider openrouter", cwd=tmp_path)
    assert code == 0

    # 6. atlas config set model.default openai/gpt-5.5
    code, out, err = run_cmd("atlas config set model.default openai/gpt-5.5", cwd=tmp_path)
    assert code == 0

    # 7. atlas config set providers.openrouter.api_key YOUR_API_KEY_HERE
    code, out, err = run_cmd("atlas config set providers.openrouter.api_key YOUR_API_KEY_HERE", cwd=tmp_path)
    assert code == 0

    # 8. atlas config show
    code, out, err = run_cmd("atlas config show", cwd=tmp_path)
    assert code == 0
    assert "YOUR_API_KEY_HERE" not in out
    
    # TOML check
    toml_path = tmp_path / ".atlas" / "config.toml"
    assert toml_path.exists()
    toml_content = toml_path.read_text()
    assert "model" in toml_content
    # Confirm canonicalization
    assert "model = \"openai/gpt-5.5\"" in toml_content
    assert "default" not in toml_content
    assert "YOUR_API_KEY_HERE" not in toml_content

    # Env check
    env_path = tmp_path / ".env.atlas"
    assert env_path.exists()
    env_content = env_path.read_text()
    assert "OPENROUTER_API_KEY=YOUR_API_KEY_HERE" in env_content

    # 9. atlas config show --effective
    code, out, err = run_cmd("atlas config show --effective", cwd=tmp_path)
    assert code == 0
    eff = json.loads(out)
    assert eff["model"]["provider"] == "openrouter"
    assert eff["model"]["model"] == "openai/gpt-5.5"
    assert "YOUR_API_KEY_HERE" not in out

    # 10. atlas model current
    code, out, err = run_cmd("atlas model current", cwd=tmp_path)
    assert code == 0
    assert "openrouter/openai/gpt-5.5" in out

    # 11. check doctor output matches spec
    code, out, err = run_cmd("atlas config doctor", cwd=tmp_path)
    assert code == 0
    assert "provider: openrouter" in out
    assert "model: openai/gpt-5.5" in out
    assert "API key: configured/redacted" in out
    assert "live trading disabled unless explicitly enabled" in out
    assert "ANTHROPIC_API_KEY" not in out
