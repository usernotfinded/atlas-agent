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
        assert "google" in out
        assert "Google Gemini" in out
        assert "google-gemini" not in out
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

    def test_list_openrouter_shows_curated_ids_and_custom_allowed_note(self, workspace, capsys):
        code = main(["model", "list", "--provider", "openrouter"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openai/gpt-5.5" in out
        assert "anthropic/claude-sonnet-4-6" in out
        assert "Custom model IDs allowed." in out

    def test_list_lmstudio_shows_examples_and_custom_allowed_note(self, workspace, capsys):
        code = main(["model", "list", "--provider", "lmstudio"])
        assert code == 0
        out = capsys.readouterr().out
        assert "llama" in out
        assert "qwen" in out
        assert "Custom model IDs allowed." in out

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
        assert "mode:" in out
        assert "api_mode:" in out
        assert "auth:" in out
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

    def test_current_shows_google_mode_and_provider_label(self, workspace, capsys):
        main(["model", "set", "google", "gemini-3.1-pro-preview"])
        capsys.readouterr()
        code = main(["model", "current"])
        assert code == 0
        out = capsys.readouterr().out
        assert "provider: Google Gemini" in out
        assert "mode:     Native Gemini API" in out


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

    def test_set_rejects_unknown_model_for_hosted_provider(self, workspace, capsys):
        code = main(["model", "set", "openai", "my-custom-model"])
        assert code == 2
        out = capsys.readouterr().out
        assert "not valid for provider 'openai'" in out

    def test_set_rejects_openai_with_anthropic_model(self, workspace, capsys):
        code = main(["model", "set", "openai", "claude-sonnet-4-6"])
        assert code == 2
        out = capsys.readouterr().out
        assert "not valid for provider 'openai'" in out

    def test_set_rejects_anthropic_with_openai_model(self, workspace, capsys):
        code = main(["model", "set", "anthropic", "gpt-5.5"])
        assert code == 2
        out = capsys.readouterr().out
        assert "not valid for provider 'anthropic'" in out

    def test_set_allows_openrouter_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "openrouter", "my-custom-openrouter-model"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openrouter/my-custom-openrouter-model" in out

    def test_set_allows_openai_compatible_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "openai-compatible", "internal-gateway-model"])
        assert code == 0
        out = capsys.readouterr().out
        assert "openai-compatible/internal-gateway-model" in out

    def test_set_allows_lmstudio_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "lmstudio", "llama-local-q8"])
        assert code == 0
        out = capsys.readouterr().out
        assert "lmstudio/llama-local-q8" in out

    def test_set_allows_local_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "local", "meta-llama/Llama-3.3-70B-Instruct"])
        assert code == 0
        out = capsys.readouterr().out
        assert "local/meta-llama/Llama-3.3-70B-Instruct" in out

    def test_set_allows_custom_endpoint_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "custom", "internal/proxy-model"])
        assert code == 0
        out = capsys.readouterr().out
        assert "custom/internal/proxy-model" in out

    def test_set_allows_nvidia_local_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "nvidia-local", "nvidia/nemotron-3-super-120b-a12b"])
        assert code == 0
        out = capsys.readouterr().out
        assert "nvidia-local/nvidia/nemotron-3-super-120b-a12b" in out

    def test_set_allows_huggingface_freeform_model(self, workspace, capsys):
        code = main(["model", "set", "huggingface", "my-org/private-model-id"])
        assert code == 0
        out = capsys.readouterr().out
        assert "huggingface/my-org/private-model-id" in out

    def test_set_allows_unknown_provider_with_warning(self, workspace, capsys):
        code = main(["model", "set", "unknown-provider", "some-model"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Warning: unknown provider" in out

    def test_rejected_cross_provider_pair_does_not_leak_into_model_current(self, workspace, capsys):
        code = main(["model", "set", "openai", "claude-3-5-sonnet-20240620"])
        assert code == 2
        capsys.readouterr()
        code = main(["model", "current"])
        assert code == 0
        out = capsys.readouterr().out
        assert "claude-3-5-sonnet-20240620" not in out

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
        main(["model", "set", "anthropic", "claude-sonnet-4-6"])
        capsys.readouterr()
        code = main(["config", "doctor"])
        assert code == 0
        out = capsys.readouterr().out
        assert "ANTHROPIC_API_KEY" in out
        assert "configured/redacted" in out
        assert "sk-ant-test" not in out

    def test_doctor_warns_about_other_provider_keys(self, workspace, capsys, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        main(["model", "set", "anthropic", "claude-sonnet-4-6"])
        capsys.readouterr()
        code = main(["config", "doctor"])
        assert code == 0
        out = capsys.readouterr().out
        assert "OPENAI_API_KEY" in out  # other provider key detected but ignored
        assert "ignored" in out.lower() or "other provider" in out.lower()

    def test_doctor_shows_missing_for_active_provider(self, workspace, capsys):
        main(["model", "set", "anthropic", "claude-sonnet-4-6"])
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


class TestModelListExactIds:
    def test_openai_list_shows_exact_raw_ids_not_prettified(self, workspace, capsys):
        code = main(["model", "list", "--provider", "openai"])
        assert code == 0
        out = capsys.readouterr().out
        assert "gpt-5.5" in out
        assert "GPT-5.5" not in out

    def test_anthropic_list_shows_exact_raw_ids_not_prettified(self, workspace, capsys):
        code = main(["model", "list", "--provider", "anthropic"])
        assert code == 0
        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" in out
        assert "Claude Sonnet" not in out

    def test_deprecated_models_not_in_normal_model_list_output(self, workspace, capsys):
        code = main(["model", "list"])
        assert code == 0
        out = capsys.readouterr().out
        assert "deepseek-chat" not in out
        assert "deepseek-reasoner" not in out
        assert "gpt-3.5-turbo" not in out
        assert "kimi-latest" not in out
        assert "grok-3" not in out
