from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from atlas_agent.cli import main


@pytest.fixture
def workspace(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    monkeypatch.setenv("HOME", str(temp_dir))
    try:
        main(["init", "."])
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


class TestModelProviders:
    def test_providers_lists_all(self, workspace, capsys):
        code = main(["model", "providers"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openrouter" in out
        assert "openai" in out
        assert "anthropic" in out
        assert "deepseek" in out
        assert "kimi" in out
        assert "nvidia" in out
        assert "xai" in out
        assert "google-gemini" in out
        assert "huggingface" in out
        assert "local" in out
        assert "custom" in out

    def test_providers_shows_key_status(self, workspace, capsys, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        code = main(["model", "providers"])
        assert code == 0
        out = capsys.readouterr().out
        assert "configured" in out


class TestModelList:
    def test_list_all_providers(self, workspace, capsys):
        code = main(["model", "list"])
        assert code == 0
        out = capsys.readouterr().out
        assert "OpenRouter" in out
        assert "openai/gpt-5.5" in out

    def test_list_filtered_provider(self, workspace, capsys):
        code = main(["model", "list", "--provider", "openai"])
        assert code == 0
        out = capsys.readouterr().out
        assert "gpt-5.5" in out
        assert "OpenAI" in out

    def test_list_unknown_provider(self, workspace, capsys):
        code = main(["model", "list", "--provider", "nonexistent"])
        assert code == 2
        out = capsys.readouterr().out
        assert "Unknown provider" in out


class TestModelCurrent:
    def test_current_shows_provider_and_model(self, workspace, capsys):
        code = main(["model", "current"])
        assert code == 0
        out = capsys.readouterr().out
        assert "provider:" in out
        assert "model:" in out
        assert "api_mode:" in out
        assert "api_key:" in out
        # Must not leak raw API key
        assert "sk-" not in out

    def test_current_shows_key_source_from_env(self, workspace, capsys, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        code = main(["model", "current"])
        assert code == 0
        out = capsys.readouterr().out
        assert "configured" in out
        assert "OPENAI_API_KEY" in out
        assert "sk-openai" not in out

    def test_current_shows_not_required_for_local(self, workspace, capsys):
        main(["model", "set", "local", "local/default"])
        capsys.readouterr()
        code = main(["model", "current"])
        assert code == 0
        out = capsys.readouterr().out
        assert "not required" in out


class TestModelSet:
    def test_set_with_provider_and_model(self, workspace, capsys):
        code = main(["model", "set", "openrouter", "openai/gpt-5.5"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openrouter/openai/gpt-5.5" in out

    def test_set_with_colon_syntax(self, workspace, capsys):
        code = main(["model", "set", "openrouter:openai/gpt-5.5"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openrouter/openai/gpt-5.5" in out

    def test_set_normalizes_provider_alias(self, workspace, capsys):
        code = main(["model", "set", "or", "openai/gpt-5.5"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openrouter/openai/gpt-5.5" in out

    def test_set_allows_unknown_model_with_warning(self, workspace, capsys):
        code = main(["model", "set", "openai", "my-custom-model"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Warning" in out
        assert "my-custom-model" in out

    def test_set_allows_unknown_provider_with_warning(self, workspace, capsys):
        code = main(["model", "set", "unknown-provider", "some-model"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Warning: unknown provider" in out

    def test_set_writes_toml_not_secrets(self, workspace):
        code = main(["model", "set", "openai", "gpt-5.5"])
        assert code == 0
        config_toml = workspace / ".atlas" / "config.toml"
        assert config_toml.exists()
        text = config_toml.read_text()
        assert "provider" in text or "model" in text
        assert "sk-" not in text  # no secrets in TOML


class TestModelConfigure:
    def test_configure_noninteractive_fails_gracefully(self, workspace, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdin", open(os.devnull))
        code = main(["model", "configure"])
        assert code == 2
        out = capsys.readouterr().out
        assert "Non-interactive" in out


class TestConfigDoctor:
    def test_doctor_checks_active_provider_key(self, workspace, capsys, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        main(["model", "set", "anthropic", "claude-sonnet-4.6"])
        capsys.readouterr()
        code = main(["config", "doctor"])
        assert code == 0
        out = capsys.readouterr().out
        assert "ANTHROPIC_API_KEY" in out
        assert "configured/redacted" in out

    def test_doctor_warns_about_other_provider_keys(self, workspace, capsys, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        main(["model", "set", "anthropic", "claude-sonnet-4.6"])
        capsys.readouterr()
        code = main(["config", "doctor"])
        assert code == 0
        out = capsys.readouterr().out
        assert "OPENAI_API_KEY" in out  # other provider key detected but ignored
        assert "ignored" in out.lower() or "other provider" in out.lower()

    def test_doctor_shows_missing_for_active_provider(self, workspace, capsys):
        main(["model", "set", "anthropic", "claude-sonnet-4.6"])
        capsys.readouterr()
        code = main(["config", "doctor"])
        assert code == 0
        out = capsys.readouterr().out
        assert "missing" in out
        assert "ANTHROPIC_API_KEY" in out

    def test_doctor_gemini_warning_when_both_keys_present(self, workspace, capsys, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "sk-google")
        monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini")
        main(["model", "set", "google-gemini", "gemini-3.1-pro-preview"])
        capsys.readouterr()
        code = main(["config", "doctor"])
        assert code == 0
        out = capsys.readouterr().out
        assert "GOOGLE_API_KEY" in out
        assert "GEMINI_API_KEY" in out
        assert "precedence" in out.lower() or "Warning" in out
