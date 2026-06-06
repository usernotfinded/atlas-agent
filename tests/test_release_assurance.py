import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the script
import sys
import os
sys.path.insert(0, os.path.abspath("scripts"))
try:
    import release_assurance
except ImportError:
    pass


def _cmd_text(cmd):
    return " ".join(str(part) for part in cmd)


@pytest.fixture
def mock_env(monkeypatch):
    original_read_text = Path.read_text
    original_exists = Path.exists

    def mock_read_text(self, *args, **kwargs):
        name = str(self)
        if "release-assurance" in name or "sha256sums" in name or name.endswith(".json") and "artifacts" not in name:
            return original_read_text(self, *args, **kwargs)
        if name == "pyproject.toml":
            return 'version = "0.6.0"'
        if name == "src/atlas_agent/__init__.py":
            return '__version__ = "0.6.0"'
        if "docs/releases/" in name:
            return "does not enable live trading\ndoes not enable provider execution\nno autonomous trading\nnot financial advice\nno pypi publish has been performed"
        if name == "CHANGELOG.md":
            return "[0.6.0]"
        if name == "README.md":
            return "Current Status (v0.6.0)"
        if name == "SECURITY.md":
            return "v0.6.0"
        return original_read_text(self, *args, **kwargs)

    def mock_exists(self, *args, **kwargs):
        name = str(self)
        if "docs/releases/" in name:
            return True
        if name == ".github/workflows/provider-audit-pack.yml":
            return True
        return original_exists(self, *args, **kwargs)

    def mock_run_cmd(cmd, check=True, cwd=None, env=None):
        text = _cmd_text(cmd)
        if "git tag -l" in text:
            return "v0.6.0\n", 0, ""
        if "git ls-remote --tags" in text:
            return "v0.6.0\n", 0, ""
        if "gh release view" in text:
            return "", 0, ""
        if "update check --dry-run" in text:
            return "Current version: 0.6.0", 0, ""
        if "from atlas_agent.update.sources" in text:
            if "v0.6.0.dev0" in text:
                return "False", 0, ""
            return "True", 0, ""
        if "audit-pack --help" in text or "verify-audit-pack --help" in text:
            return "", 0, ""
        if "git diff HEAD --name-only" in text:
            return "", 0, ""
        return "", 0, ""

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    monkeypatch.setattr(Path, "exists", mock_exists)
    monkeypatch.setattr("release_assurance.run_cmd", mock_run_cmd)
    return original_read_text

def test_release_assurance_valid(mock_env, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["release_assurance.py", "--version", "v0.6.0", "--output", str(tmp_path)])
    
    with pytest.raises(SystemExit) as e:
        release_assurance.main()
    
    assert e.value.code == 0
    
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary["valid"] is True
    assert summary["public_release_detected"] is True
    assert summary["pypi_published"] is False
    assert summary["checks"]["package_version_aligned"] is True
    assert summary["checks"]["updater_dry_run_ok"] is True
    assert summary["checks"]["dev_version_not_public_stable"] is True

    report = (tmp_path / "release-assurance-report.md").read_text()
    assert "Security Hardening Included" in report
    assert "Provider Audit Evidence Included" in report
    assert "Updater Delivery Verification" in report
    assert "Safety Non-Claims" in report
    assert "no live trading enabled by default" in report
    
    assert (tmp_path / "sha256sums.txt").exists()

def test_release_assurance_uses_argument_list_subprocess() -> None:
    text = Path("scripts/release_assurance.py").read_text(encoding="utf-8")
    assert "shell=True" not in text

def test_release_assurance_invalid_version(mock_env, tmp_path, monkeypatch):
    def bad_read_text(self, *args, **kwargs):
        name = str(self)
        if "release-assurance" in name or "sha256sums" in name or name.endswith(".json") and "artifacts" not in name:
            return mock_env(self, *args, **kwargs)
        if name == "pyproject.toml":
            return 'version = "0.5.8"'
        if name == "src/atlas_agent/__init__.py":
            return '__version__ = "0.6.0"'
        if "docs/releases/" in name:
            return "does not enable live trading\ndoes not enable provider execution\nno autonomous trading\nnot financial advice\nno pypi publish has been performed"
        if name == "CHANGELOG.md":
            return "[0.6.0]"
        if name == "README.md":
            return "Current Status (v0.6.0)"
        if name == "SECURITY.md":
            return "v0.6.0"
        return mock_env(self, *args, **kwargs)
        
    monkeypatch.setattr(Path, "read_text", bad_read_text)
    monkeypatch.setattr("sys.argv", ["release_assurance.py", "--version", "v0.6.0", "--output", str(tmp_path)])
    
    with pytest.raises(SystemExit) as e:
        release_assurance.main()
    
    assert e.value.code == 1
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary["checks"]["package_version_aligned"] is False
    assert summary["valid"] is False

def test_release_assurance_missing_release_notes(mock_env, tmp_path, monkeypatch):
    original_exists = Path.exists
    def bad_exists(self, *args, **kwargs):
        if "docs/releases/" in str(self):
            return False
        if str(self) == ".github/workflows/provider-audit-pack.yml":
            return True
        return original_exists(self, *args, **kwargs)
    
    monkeypatch.setattr(Path, "exists", bad_exists)
    monkeypatch.setattr("sys.argv", ["release_assurance.py", "--version", "v0.6.0", "--output", str(tmp_path)])
    
    with pytest.raises(SystemExit) as e:
        release_assurance.main()
        
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary["checks"]["release_notes_present"] is False
    assert summary["valid"] is False

def test_release_assurance_stale_readme(mock_env, tmp_path, monkeypatch):
    def bad_read_text(self, *args, **kwargs):
        name = str(self)
        if "release-assurance" in name or "sha256sums" in name or name.endswith(".json") and "artifacts" not in name:
            return mock_env(self, *args, **kwargs)
        if name == "README.md":
            return "Current Status (v0.5.8.1)"
        if name == "pyproject.toml":
            return 'version = "0.6.0"'
        if name == "src/atlas_agent/__init__.py":
            return '__version__ = "0.6.0"'
        if "docs/releases/" in name:
            return "does not enable live trading\ndoes not enable provider execution\nno autonomous trading\nnot financial advice\nno pypi publish has been performed"
        if name == "CHANGELOG.md":
            return "[0.6.0]"
        if name == "SECURITY.md":
            return "v0.6.0"
        return mock_env(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", bad_read_text)
    monkeypatch.setattr("sys.argv", ["release_assurance.py", "--version", "v0.6.0", "--output", str(tmp_path)])
    
    with pytest.raises(SystemExit) as e:
        release_assurance.main()
        
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary["checks"]["readme_public_metadata_current"] is False

def test_release_assurance_dev_stable_check(mock_env, tmp_path, monkeypatch):
    def bad_run_cmd(cmd, check=True, cwd=None, env=None):
        text = _cmd_text(cmd)
        if "from atlas_agent.update.sources" in text:
            return "True", 0, "" # Fails dev check
        if "git diff HEAD --name-only" in text:
            return "", 0, ""
        if "git tag -l" in text:
            return "v0.6.0\n", 0, ""
        if "git ls-remote" in text:
            return "v0.6.0\n", 0, ""
        if "update check" in text:
            return "Current version: 0.6.0", 0, ""
        return "", 0, ""

    monkeypatch.setattr("release_assurance.run_cmd", bad_run_cmd)
    monkeypatch.setattr("sys.argv", ["release_assurance.py", "--version", "v0.6.0", "--output", str(tmp_path)])
    
    with pytest.raises(SystemExit) as e:
        release_assurance.main()
        
    summary = json.loads((tmp_path / "release-assurance-summary.json").read_text())
    assert summary["checks"]["dev_version_not_public_stable"] is False
    assert summary["valid"] is False

def test_release_assurance_secrets_omitted(mock_env, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["release_assurance.py", "--version", "v0.6.0", "--output", str(tmp_path)])
    with pytest.raises(SystemExit):
        release_assurance.main()
        
    report = (tmp_path / "release-assurance-report.md").read_text()
    assert "token" not in report.lower()
    assert "secret" not in report.lower() or "secret regression coverage" in report.lower() # allowed in heading
    assert "password" not in report.lower()
