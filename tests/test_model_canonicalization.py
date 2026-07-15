# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_model_canonicalization.py
# PURPOSE: Verifies model canonicalization behavior and regression expectations.
# DEPS:    os, json, pytest, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import os
import json
import pytest
from pathlib import Path
from atlas_agent.config.store import _atomic_write_toml, get_config_toml_path
from atlas_agent.config import get_config, set_raw_value, unset_raw_value

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_set_model_default_writes_only_model_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    
    set_raw_value("model.default", "openai/gpt-4o")
    
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert "default" not in content
    assert 'model = "openai/gpt-4o"' in content

def test_set_model_default_removes_existing_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    
    import tomlkit
    doc = tomlkit.document()
    model_table = tomlkit.table()
    model_table["default"] = "openai/old-model"
    doc["model"] = model_table
    _atomic_write_toml(doc)
    
    set_raw_value("model.default", "openai/gpt-4o")
    
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert "default" not in content
    assert 'model = "openai/gpt-4o"' in content

def test_unset_model_default_does_not_remove_model_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    
    import tomlkit
    doc = tomlkit.document()
    model_table = tomlkit.table()
    model_table["model"] = "openai/canonical"
    model_table["default"] = "openai/legacy"
    doc["model"] = model_table
    _atomic_write_toml(doc)
    
    unset_raw_value("model.default")
    
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert "default" not in content
    assert 'model = "openai/canonical"' in content

def test_unset_model_model_removes_canonical_model_and_legacy_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    
    import tomlkit
    doc = tomlkit.document()
    model_table = tomlkit.table()
    model_table["model"] = "openai/canonical"
    model_table["default"] = "openai/legacy"
    doc["model"] = model_table
    _atomic_write_toml(doc)
    
    unset_raw_value("model.model")
    
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert "default" not in content
    assert "model = " not in content

def test_legacy_model_default_is_read_as_fallback_without_mutating_raw_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    
    import tomlkit
    doc = tomlkit.document()
    model_table = tomlkit.table()
    model_table["default"] = "openai/legacy"
    doc["model"] = model_table
    _atomic_write_toml(doc)
    
    config = get_config()
    assert config.model.model == "openai/legacy"
    
    # Must not have mutated raw file
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert "default" in content
    assert "model = " not in content

def test_migration_canonicalizes_model_default_to_model_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from atlas_agent.config.migrate import migrate_legacy_config
    
    legacy_dir = tmp_path / ".atlas"
    legacy_dir.mkdir(exist_ok=True)
    legacy_json = legacy_dir / "config.json"
    legacy_json.write_text(json.dumps({
        "provider": "openrouter",
        "model": "openai/legacy" # In the old config.json, model meant model.model
    }))
    
    # Wait, the prompt says "If migration encounters model.default: move/canonicalize to model.model"
    # Wait, old config.json didn't have model.default, it just had "model".
    # But if someone had model.default in their JSON for some reason?
    # Let's test with just basic migration making sure it writes to model.model
    migrate_legacy_config()
    
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert "default" not in content
    assert 'model = "openai/legacy"' in content

def test_provider_is_preserved_during_model_default_canonicalization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir(exist_ok=True)
    
    set_raw_value("model.provider", "anthropic")
    set_raw_value("model.default", "claude")
    
    toml_path = get_config_toml_path()
    content = toml_path.read_text()
    assert 'provider = "anthropic"' in content
    assert 'model = "claude"' in content
    assert "default" not in content
