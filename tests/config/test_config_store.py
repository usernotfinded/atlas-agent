import pytest
from pathlib import Path
from atlas_agent.config.store import set_raw_value, get_raw_value, load_raw_config
from atlas_agent.config.paths import get_config_toml_path

def test_config_store_rejects_secrets_without_exposure(monkeypatch, tmp_path):
    # Mock get_workspace_root so config writes to tmp_path
    monkeypatch.setattr("atlas_agent.config.paths.get_workspace_root", lambda: tmp_path)
    
    secret_key = "OPENAI_API_KEY"
    secret_value = "sk-super-secret-12345"
    
    with pytest.raises(ValueError) as excinfo:
        set_raw_value(secret_key, secret_value)
        
    err_msg = str(excinfo.value)
    
    # Assert the key is mentioned in the error message for UX
    assert secret_key in err_msg
    # Assert the secret VALUE is NOT exposed in the error message
    assert secret_value not in err_msg
    assert "sk-" not in err_msg

def test_config_store_atomic_write(monkeypatch, tmp_path):
    monkeypatch.setattr("atlas_agent.config.paths.get_workspace_root", lambda: tmp_path)
    
    set_raw_value("market.symbol", "AAPL")
    val = get_raw_value("market.symbol")
    assert val == "AAPL"
    
    # Verify the file was written
    toml_path = get_config_toml_path()
    assert toml_path.exists()
    
    # In UNIX mkstemp creates files with 0o600 permissions
    import os
    if os.name != "nt":
        st = os.stat(toml_path)
        # Check that it's not world readable
        assert (st.st_mode & 0o077) == 0
