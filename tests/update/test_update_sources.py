# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/update/test_update_sources.py
# PURPOSE: Verifies update sources behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import pytest
from atlas_agent.update.sources import is_public_stable, is_version_newer, GitHubReleaseSource, UpdateSourceError

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_is_public_stable():
    assert is_public_stable("0.5.9") is True
    assert is_public_stable("v0.5.9") is True
    assert is_public_stable("0.5.9.dev0") is False
    assert is_public_stable("v0.5.9.dev0") is False
    assert is_public_stable("0.5.9-rc1") is False

def test_is_version_newer():
    assert is_version_newer("0.5.9", "0.5.8.1") is True
    assert is_version_newer("0.5.8.1", "0.5.9") is False

def test_github_release_source_rejects_dev(monkeypatch):
    def fake_fetch_json(url):
        return {"tag_name": "v0.5.9.dev0", "body": "dev release"}
    
    source = GitHubReleaseSource(repo="foo/bar", fetch_json=fake_fetch_json)
    result = source.check("0.5.8")
    assert result is None

def test_github_release_source_accepts_stable(monkeypatch):
    def fake_fetch_json(url):
        return {"tag_name": "v0.5.9", "body": "stable release"}
    
    source = GitHubReleaseSource(repo="foo/bar", fetch_json=fake_fetch_json)
    result = source.check("0.5.8.1")
    assert result is not None
    assert result.latest_version == "0.5.9"

def test_github_release_source_malformed_metadata(monkeypatch):
    def fake_fetch_json(url):
        return [] # malformed
    
    source = GitHubReleaseSource(repo="foo/bar", fetch_json=fake_fetch_json)
    result = source.check("0.5.8")
    assert result is None

def test_github_release_source_unavailable(monkeypatch):
    def fake_fetch_json(url):
        raise UpdateSourceError("network down")
    
    source = GitHubReleaseSource(repo="foo/bar", fetch_json=fake_fetch_json)
    with pytest.raises(UpdateSourceError):
        source.check("0.5.8")
