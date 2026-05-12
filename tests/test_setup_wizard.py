import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.setup.wizard_ui import (
    CUSTOM_MODEL_ID_CHOICE,
    CUSTOM_MODEL_ID_LABEL,
    WizardApplication,
)
from atlas_agent.setup.renderer import render_wizard_screen
from atlas_agent.setup.state import WizardState

def test_wizard_hides_local_command_and_null():
    state = WizardState()
    state.setup_mode = "full"
    app = WizardApplication(state)
    app.current_step = "provider"
    app.update_step_data()
    choice_ids = [c[0] for c in app.choices]
    assert "local_command" not in choice_ids
    assert "null" not in choice_ids
    assert "google" in choice_ids
    assert "google-gemini" not in choice_ids
    assert "gemini-openai-compatible" not in choice_ids
    assert "lmstudio" in choice_ids
    assert "openai-compatible" in choice_ids

def test_wizard_google_provider_opens_mode_step():
    state = WizardState()
    app = WizardApplication(state)
    app.current_step = "provider"
    app.state.provider = "google"
    app.next_step()
    assert app.current_step == "google_api_mode"
    assert "Native Gemini API" in app.title
    assert "OpenAI-compatible endpoint" in app.title

def test_wizard_google_oauth_does_not_ask_for_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN", raising=False)

    state = WizardState(provider="google")
    app = WizardApplication(state)
    app.current_step = "google_auth_method"
    app.state.google_auth_method = "oauth_adc"
    app.next_step()
    assert app.current_step == "google_oauth_adc_check"
    assert "readiness check" in app.title.lower()
    assert "Enter GOOGLE_API_KEY" not in app.title

def test_wizard_lmstudio_does_not_require_api_key_step():
    state = WizardState(provider="lmstudio")
    app = WizardApplication(state)
    app.current_step = "provider"
    app.next_step()
    assert app.current_step == "custom_endpoint"
    app.next_step()
    assert app.current_step == "model"
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices

def test_wizard_openai_compatible_prompts_optional_key_after_base_url():
    state = WizardState(provider="openai-compatible")
    app = WizardApplication(state)
    app.current_step = "provider"
    app.next_step()
    assert app.current_step == "custom_endpoint"
    app.next_step()
    assert app.current_step == "optional_api_key_choice"
    assert any("Provide API key" in label for _, label in app.choices)

def test_wizard_api_key_input_is_visible():
    state = WizardState()
    lines = render_wizard_screen(
        state=state,
        current_step="api_key_input",
        choices=[],
        current_index=0,
        input_value="my-secret-key",
        title="Enter Key",
        is_password=False
    )
    text = "".join(line[1] for line in lines)
    assert "my-secret-key" in text
    assert "******" not in text

def test_wizard_summary_redacts_api_key():
    state = WizardState()
    state.credentials_configured = True
    lines = render_wizard_screen(
        state=state,
        current_step="model",
        choices=[],
        current_index=0,
        input_value="",
        title="Select Model",
        is_password=False
    )
    text = "".join(line[1] for line in lines)
    assert "API Key: configured" in text
    assert "my-secret-key" not in text


def test_wizard_summary_shows_model_not_selected_when_empty():
    state = WizardState(provider="openai", model="")
    lines = render_wizard_screen(
        state=state,
        current_step="messaging",
        choices=[],
        current_index=0,
        title="Messaging",
    )
    text = "".join(line[1] for line in lines)
    assert "Model: not selected" in text


def test_provider_change_resets_stale_model_and_provider_state():
    state = WizardState(
        provider="anthropic",
        model="claude-opus-4-7",
        google_api_mode="openai_compatible",
        google_auth_method="oauth_adc",
        custom_endpoint="https://old-endpoint.example/v1",
        credentials_configured=True,
    )
    app = WizardApplication(state)
    app._apply_provider_selection("openai")

    assert state.provider == "openai"
    assert state.model == "gpt-5.5"
    assert state.google_api_mode == "native"
    assert state.google_auth_method == "api_key"
    assert state.custom_endpoint is None
    assert state.credentials_configured is False

    lines = render_wizard_screen(
        state=state,
        current_step="messaging",
        choices=[],
        current_index=0,
        title="Select model",
    )
    text = "".join(chunk for _, chunk in lines)
    assert "provider: openai".lower() in text.lower()
    assert "claude-opus-4-7" not in text


def test_openai_model_choices_are_provider_scoped():
    state = WizardState(provider="openai")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert "gpt-5.5" in ids
    assert all("claude" not in model_id for model_id in ids)
    assert "gpt-3.5-turbo" not in ids
    assert ids == [label for _, label in app.choices]


def test_anthropic_model_choices_are_provider_scoped():
    state = WizardState(provider="anthropic")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert ids == [
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
    ]
    assert all("gpt-" not in model_id for model_id in ids)
    assert ids == [label for _, label in app.choices]


def test_google_model_choices_are_provider_scoped():
    state = WizardState(provider="google")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert ids == [
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
    ]
    assert all("claude" not in model_id for model_id in ids)
    assert all("gpt-" not in model_id for model_id in ids)
    assert "gemini-3.1-flash-lite-preview" not in ids
    assert ids == [label for _, label in app.choices]


def test_deepseek_model_choices_are_provider_scoped():
    state = WizardState(provider="deepseek")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert ids == ["deepseek-v4-pro", "deepseek-v4-flash"]
    assert "gpt-4o" not in ids


def test_kimi_model_choices_are_provider_scoped():
    state = WizardState(provider="kimi")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert "kimi-k2.6" in ids
    assert "kimi-latest" not in ids
    assert "kimi-thinking-preview" not in ids


def test_xai_model_choices_are_provider_scoped():
    state = WizardState(provider="xai")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert ids == ["grok-4.3", "grok-4.20", "grok-4.20-reasoning", "grok-4.20-non-reasoning"]
    assert "grok-3" not in ids
    assert "grok-4" not in ids
    assert "grok-code-fast-1" not in ids


def test_nvidia_cloud_model_choices_are_curated_text_examples_only():
    state = WizardState(provider="nvidia")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert "nvidia/llama-3.3-nemotron-super-49b-v1.5" in ids
    assert "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning" not in ids
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices


def test_local_self_hosted_uses_freeform_model_input_step():
    state = WizardState(provider="local")
    app = WizardApplication(state)
    app.current_step = "provider"
    app.next_step()
    assert app.current_step == "model"
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices


def test_nvidia_local_uses_freeform_model_input_step():
    state = WizardState(provider="nvidia-local")
    app = WizardApplication(state)
    app.current_step = "provider"
    app.next_step()
    assert app.current_step == "model"
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices


def test_openrouter_uses_freeform_model_input_step():
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    app.current_step = "provider"
    app.next_step()
    assert app.current_step in {"api_key_input", "api_key_check"}


def test_openrouter_model_step_shows_curated_ids_plus_custom_option():
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert "openai/gpt-5.5" in ids
    assert "anthropic/claude-sonnet-4-6" in ids
    assert "google/gemini-3-flash-preview" in ids
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices


def test_openrouter_curated_selection_stores_exact_model_id():
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    assert app._apply_model_choice("openai/gpt-5.5") is True
    assert state.model == "openai/gpt-5.5"


def test_openrouter_custom_model_selection_stores_typed_exact_id():
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    assert app._apply_model_choice(CUSTOM_MODEL_ID_CHOICE) is False
    assert app.current_step == "model_input"
    app.input_value = "some/private-openrouter-model"
    assert app._commit_model_input() is True
    assert state.model == "some/private-openrouter-model"


def test_custom_model_input_rejects_empty_string():
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    app._apply_model_choice(CUSTOM_MODEL_ID_CHOICE)
    app.input_value = ""
    assert app._commit_model_input() is False
    assert app.title == "Model ID is required."


def test_selected_so_far_shows_exact_custom_model_id():
    state = WizardState(provider="openrouter")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    app._apply_model_choice(CUSTOM_MODEL_ID_CHOICE)
    app.input_value = "my-org/private-chat-model-v2"
    assert app._commit_model_input() is True
    lines = render_wizard_screen(
        state=state,
        current_step="messaging",
        choices=[],
        current_index=0,
        title="Messaging",
    )
    text = "".join(chunk for _, chunk in lines)
    assert "my-org/private-chat-model-v2" in text


def test_lmstudio_model_step_shows_examples_plus_custom_option():
    state = WizardState(provider="lmstudio")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert "llama" in ids
    assert "qwen" in ids
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices


def test_openai_compatible_model_step_shows_examples_plus_custom_option():
    state = WizardState(provider="openai-compatible")
    app = WizardApplication(state)
    app.current_step = "model"
    app.update_step_data()
    ids = [model_id for model_id, _ in app.choices]
    assert "deepseek-v4-flash" in ids
    assert "local-model" in ids
    assert (CUSTOM_MODEL_ID_CHOICE, CUSTOM_MODEL_ID_LABEL) in app.choices


def test_regression_openai_selection_never_shows_stale_claude_model():
    state = WizardState(provider="anthropic", model="claude-3-5-sonnet-20240620")
    app = WizardApplication(state)
    app._apply_provider_selection("openai")

    lines = render_wizard_screen(
        state=state,
        current_step="messaging",
        choices=[],
        current_index=0,
        title="dummy",
    )
    text = "".join(chunk for _, chunk in lines)
    assert "claude-3-5-sonnet-20240620" not in text
    assert "gpt-5.5" in text
from atlas_agent.setup.wizard import is_interactive
from atlas_agent.cli import main

def test_wizard_state_default():
    state = WizardState()
    assert state.setup_mode == "quick"
    assert state.messaging == "cli"

def test_wizard_state_serialization(tmp_path):
    config_file = tmp_path / "config.json"
    state = WizardState(
        setup_mode="full",
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="telegram",
        workspace_path="/tmp/workspace",
        trust_mode="live",
        broker_mode="alpaca",
        update_channel="beta"
    )
    state.save(config_file)
    
    assert config_file.exists()
    
    loaded = WizardState.load(config_file)
    assert loaded.setup_mode == "full"
    assert loaded.provider == "anthropic"
    assert loaded.model == "claude-opus-4-7"
    assert loaded.messaging == "telegram"
    assert loaded.workspace_path == "/tmp/workspace"
    assert loaded.trust_mode == "live"
    assert loaded.broker_mode == "alpaca"
    assert loaded.update_channel == "beta"

def test_wizard_state_load_nonexistent(tmp_path):
    missing_file = tmp_path / "missing.json"
    state = WizardState.load(missing_file)
    assert state.setup_mode == "quick"

def test_wizard_state_load_invalid(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("invalid json")
    state = WizardState.load(bad_file)
    assert state.setup_mode == "quick"


def test_wizard_state_save_rejects_incompatible_provider_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = WizardState(
        provider="openai",
        model="claude-sonnet-4-6",
        credentials_configured=True,
    )
    with pytest.raises(ValueError, match="not valid for provider 'openai'"):
        state.save(tmp_path / ".atlas" / "config.json")

@patch("atlas_agent.setup.wizard.is_interactive")
def test_cli_configure_non_interactive(mock_is_interactive, capsys):
    mock_is_interactive.return_value = False
    
    code = main(["configure"])
    assert code == 2
    
    captured = capsys.readouterr()
    assert "Non-interactive mode detected" in captured.out
    
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_cli_configure_success(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = True
    
    monkeypatch.chdir(tmp_path)
    
    code = main(["configure"])
    assert code == 0
    assert (tmp_path / ".atlas/config.json").exists()
    
@patch("atlas_agent.setup.wizard.is_interactive")
@patch("atlas_agent.setup.wizard.run_wizard")
def test_cli_configure_cancel(mock_run_wizard, mock_is_interactive, tmp_path, monkeypatch, capsys):
    mock_is_interactive.return_value = True
    mock_run_wizard.return_value = False
    
    monkeypatch.chdir(tmp_path)
    
    code = main(["configure"])
    assert code == 130
    
    captured = capsys.readouterr()
    assert "Setup cancelled." in captured.out
