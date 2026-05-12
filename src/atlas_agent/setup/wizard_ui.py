import os
from pathlib import Path
from typing import Any, List, Tuple

from prompt_toolkit import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout

from atlas_agent.providers.catalog import (
    GOOGLE_PROVIDER_ID,
    get_provider_profile,
    list_provider_profiles,
)
from atlas_agent.setup.renderer import render_wizard_screen
from atlas_agent.setup.state import WizardState
from atlas_agent.setup.theme import atlas_theme


class WizardApplication:
    def __init__(self, state: WizardState):
        self.state = state
        self.current_step = "setup_mode"
        self.history: List[str] = []
        self.current_index = 0
        self.input_value = ""
        self.choices: List[Tuple[str, str]] = []
        self.title = ""
        self.temp_secrets: dict[str, str] = {}
        self.google_oauth_ready = False
        self.google_oauth_messages: list[str] = []
        self.update_step_data()

    def _provider_profile(self):
        return get_provider_profile(self.state.provider)

    @staticmethod
    def _provider_uses_custom_endpoint(provider_id: str) -> bool:
        return provider_id in ("lmstudio", "openai-compatible", "custom")

    @staticmethod
    def _provider_uses_freeform_model(provider_id: str) -> bool:
        return provider_id in ("lmstudio", "openai-compatible", "custom")

    @staticmethod
    def _provider_supports_optional_api_key(provider_id: str) -> bool:
        return provider_id in ("openai-compatible", "custom")

    @staticmethod
    def _default_key_name(provider_id: str) -> str:
        profile = get_provider_profile(provider_id)
        if profile and profile.env_precedence:
            return profile.env_precedence[0]
        return f"{provider_id.upper()}_API_KEY"

    @staticmethod
    def _google_oauth_adc_check() -> tuple[bool, list[str]]:
        messages: list[str] = []

        for env_var in ("ATLAS_GOOGLE_OAUTH_ACCESS_TOKEN", "GOOGLE_OAUTH_ACCESS_TOKEN"):
            if os.getenv(env_var):
                messages.append(f"Detected explicit OAuth bearer token via {env_var}.")
                return (True, messages)

        adc_env_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        if adc_env_path:
            adc_path = Path(adc_env_path).expanduser()
            if adc_path.exists():
                messages.append(f"Detected GOOGLE_APPLICATION_CREDENTIALS file: {adc_path}")
                return (True, messages)
            messages.append(f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {adc_path}")

        adc_default = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
        if adc_default.exists():
            messages.append(f"Detected gcloud Application Default Credentials file: {adc_default}")
            return (True, messages)

        messages.append("No Google OAuth/ADC credentials were detected.")
        messages.append("Remediation: set GOOGLE_APPLICATION_CREDENTIALS or run `gcloud auth application-default login`.")
        return (False, messages)

    def _has_key_in_env(self, provider_id: str) -> bool:
        profile = get_provider_profile(provider_id)
        if not profile:
            return False
        return any(bool(os.getenv(var)) for var in profile.env_precedence)

    def update_step_data(self):
        if self.current_step == "setup_mode":
            self.title = "How would you like to set up Atlas Agent?"
            self.choices = [
                ("quick", "Quick setup — provider, model & messaging (recommended)"),
                ("full", "Full setup — configure everything"),
            ]
            self.current_index = 0 if self.state.setup_mode == "quick" else 1
            return

        if self.current_step == "provider":
            self.title = "Select provider:"
            self.choices = [(p.id, p.label) for p in list_provider_profiles() if p.include_in_wizard]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.provider), 0)
            return

        if self.current_step == "google_api_mode":
            self.title = (
                "Google Gemini API mode:\n"
                "Native Gemini API:\n"
                "- recommended default\n"
                "- uses Gemini-native API behavior\n"
                "- best future compatibility with Gemini-specific features\n\n"
                "OpenAI-compatible endpoint:\n"
                "- useful when reusing OpenAI-compatible clients/adapters\n"
                "- uses Gemini's OpenAI-compatible endpoint\n"
                "- may not expose every Gemini-native feature"
            )
            self.choices = [
                ("native", "Native Gemini API (recommended default)"),
                ("openai_compatible", "OpenAI-compatible endpoint"),
            ]
            self.current_index = 0 if self.state.google_api_mode == "native" else 1
            return

        if self.current_step == "google_auth_method":
            self.title = "Google Gemini authentication method:"
            self.choices = [
                ("api_key", "API key (recommended default)"),
                ("oauth_adc", "OAuth / Application Default Credentials"),
            ]
            self.current_index = 0 if self.state.google_auth_method == "api_key" else 1
            return

        if self.current_step == "google_oauth_adc_check":
            self.google_oauth_ready, self.google_oauth_messages = self._google_oauth_adc_check()
            status = "Credentials detected." if self.google_oauth_ready else "Credentials missing."
            detail = "\n".join(f"- {line}" for line in self.google_oauth_messages)
            self.title = (
                "Google OAuth / ADC readiness check:\n"
                f"{status}\n\n"
                f"{detail}\n"
            )
            if self.google_oauth_ready:
                self.choices = [
                    ("continue", "Continue with OAuth / ADC"),
                    ("back", "Back"),
                ]
            else:
                self.choices = [
                    ("retry", "Retry credential check"),
                    ("back", "Back to auth method"),
                ]
            self.current_index = 0
            return

        if self.current_step == "api_key_check":
            key_name = self._default_key_name(self.state.provider)
            self.title = f"API Key Detection: {key_name} detected from environment."
            self.choices = [
                ("use_existing", "Use existing from environment"),
                ("replace", "Replace / Enter manually"),
                ("skip", "Skip for now"),
            ]
            self.current_index = 0
            return

        if self.current_step == "api_key_input":
            key_name = self._default_key_name(self.state.provider)
            self.title = f"Enter {key_name}:"
            self.choices = []
            self.input_value = ""
            return

        if self.current_step == "custom_endpoint":
            if self.state.provider == "lmstudio":
                self.title = "Enter LM Studio BASE URL (default: http://localhost:1234/v1):"
                self.input_value = self.state.custom_endpoint or "http://localhost:1234/v1"
            elif self.state.provider in ("openai-compatible", "custom"):
                self.title = f"Enter {self.state.provider} BASE URL:"
                self.input_value = self.state.custom_endpoint or ""
            else:
                self.title = "Enter BASE URL:"
                self.input_value = self.state.custom_endpoint or ""
            self.choices = []
            return

        if self.current_step == "optional_api_key_choice":
            key_name = self._default_key_name(self.state.provider)
            self.title = (
                f"Optional API key for {self.state.provider}:\n"
                f"- provide {key_name} now, or skip\n"
                "- if skipped, runtime sends no Authorization header"
            )
            self.choices = [
                ("set_key", "Provide API key"),
                ("skip_key", "Skip API key"),
            ]
            self.current_index = 1 if not self.state.credentials_configured else 0
            return

        if self.current_step == "model_input":
            profile = self._provider_profile()
            default_model = self.state.model or (profile.default_model if profile else "")
            self.title = (
                f"Enter model ID for {profile.label if profile else self.state.provider}:\n"
                f"(press Enter to keep: {default_model})"
            )
            self.choices = []
            self.input_value = default_model
            return

        if self.current_step == "model":
            profile = self._provider_profile()
            if self.state.provider == "local_command":
                self.title = "WARNING: Local command provider is legacy compatibility only.\nSelect model:"
            elif profile:
                self.title = f"Select model for {profile.label}:"
            else:
                self.title = f"Select model for {self.state.provider}:"
            if profile and profile.models:
                self.choices = [(m.id, m.label) for m in profile.models]
            else:
                self.choices = [("default", "Default Model")]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.model), 0)
            return

        if self.current_step == "research_provider":
            self.title = "Optional web research provider:"
            self.choices = [
                ("skip", "Skip for now"),
                ("custom", "Custom search/research API"),
                ("local", "Self-hosted/local provider"),
                ("existing", "Existing environment variable"),
                ("legacy_perplexity", "Legacy Perplexity backend"),
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.research_provider), 0)
            return

        if self.current_step == "research_api_key_input":
            self.title = "Enter ATLAS_RESEARCH_API_KEY (or legacy PERPLEXITY_API_KEY):"
            self.choices = []
            self.input_value = ""
            return

        if self.current_step == "messaging":
            self.title = "Select messaging integration:"
            self.choices = [
                ("cli", "CLI only"),
                ("telegram", "Telegram (experimental)"),
                ("none", "None"),
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.messaging), 0)
            return

        if self.current_step == "workspace_path":
            self.title = "Workspace:"
            self.choices = []
            self.input_value = self.state.workspace_path
            return

        if self.current_step == "trust_mode":
            self.title = "Select execution trust mode:"
            self.choices = [
                ("paper", "Paper Trading"),
                ("live", "Live Trading (Requires Approval)"),
            ]
            self.current_index = 0 if self.state.trust_mode == "paper" else 1
            return

        if self.current_step == "broker_mode":
            self.title = "Select broker mode:"
            self.choices = [
                ("paper", "Paper Broker"),
                ("alpaca", "Alpaca"),
                ("binance", "Binance"),
                ("ccxt", "CCXT (Generic)"),
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.broker_mode), 0)
            return

        if self.current_step == "update_channel":
            self.title = "Select update channel:"
            self.choices = [
                ("stable", "Stable"),
                ("beta", "Beta"),
            ]
            self.current_index = 0 if self.state.update_channel == "stable" else 1
            return

        if self.current_step == "review":
            self.title = "Review your configuration:"
            self.choices = [
                ("save", "Save and exit"),
                ("back", "Back"),
                ("cancel", "Cancel"),
            ]
            self.current_index = 0

    def next_step(self):
        self.history.append(self.current_step)

        if self.current_step == "setup_mode":
            self.current_step = "provider"
        elif self.current_step == "provider":
            profile = self._provider_profile()
            if not profile:
                self.current_step = "model"
            elif profile.id == GOOGLE_PROVIDER_ID:
                self.current_step = "google_api_mode"
            elif self._provider_uses_custom_endpoint(profile.id):
                self.current_step = "custom_endpoint"
            elif profile.key_required:
                self.current_step = "api_key_check" if self._has_key_in_env(profile.id) else "api_key_input"
            else:
                self.current_step = "model"
        elif self.current_step == "google_api_mode":
            self.current_step = "google_auth_method"
        elif self.current_step == "google_auth_method":
            if self.state.google_auth_method == "api_key":
                self.current_step = "api_key_check" if self._has_key_in_env(GOOGLE_PROVIDER_ID) else "api_key_input"
            else:
                self.current_step = "google_oauth_adc_check"
        elif self.current_step == "google_oauth_adc_check":
            self.current_step = "model"
        elif self.current_step == "api_key_check":
            # handled directly in run()
            pass
        elif self.current_step == "api_key_input":
            if self._provider_uses_freeform_model(self.state.provider):
                self.current_step = "model_input"
            else:
                self.current_step = "model"
        elif self.current_step == "custom_endpoint":
            if self._provider_supports_optional_api_key(self.state.provider):
                self.current_step = "optional_api_key_choice"
            elif self._provider_uses_freeform_model(self.state.provider):
                self.current_step = "model_input"
            else:
                self.current_step = "model"
        elif self.current_step == "optional_api_key_choice":
            # handled directly in run()
            pass
        elif self.current_step == "model_input":
            self.current_step = "research_provider"
        elif self.current_step == "model":
            self.current_step = "research_provider"
        elif self.current_step == "research_provider":
            if self.state.research_provider in ["custom", "legacy_perplexity"]:
                self.current_step = "research_api_key_input"
            else:
                self.current_step = "messaging"
        elif self.current_step == "research_api_key_input":
            self.current_step = "messaging"
        elif self.current_step == "messaging":
            self.current_step = "workspace_path" if self.state.setup_mode == "full" else "review"
        elif self.current_step == "workspace_path":
            self.current_step = "trust_mode"
        elif self.current_step == "trust_mode":
            self.current_step = "broker_mode"
        elif self.current_step == "broker_mode":
            self.current_step = "update_channel"
        elif self.current_step == "update_channel":
            self.current_step = "review"

        self.update_step_data()

    def back_step(self):
        if self.history:
            self.current_step = self.history.pop()
            self.update_step_data()

    def save_secrets(self):
        if not self.temp_secrets:
            return

        from atlas_agent.config import set_secret

        for key, value in self.temp_secrets.items():
            set_secret(key, value)

        # Maintain backward compatibility for tests that expect .gitignore update
        self.ensure_gitignore(".env.atlas")

    def ensure_gitignore(self, entry: str):
        gitignore = Path(".gitignore")
        if not gitignore.exists():
            gitignore.write_text(f"{entry}\n", encoding="utf-8")
            return

        content = gitignore.read_text(encoding="utf-8")
        if entry not in content.splitlines():
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write(f"\n{entry}\n")

    def run(self) -> bool:
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if self.choices:
                self.current_index = max(0, self.current_index - 1)

        @kb.add("down")
        def _(event):
            if self.choices:
                self.current_index = min(len(self.choices) - 1, self.current_index + 1)

        @kb.add("enter")
        @kb.add("space", filter=Condition(lambda: bool(self.choices)))
        def _(event):
            if self.choices:
                val = self.choices[self.current_index][0]

                if self.current_step == "review":
                    if val == "save":
                        self.save_secrets()
                        event.app.exit(result=True)
                    elif val == "back":
                        self.back_step()
                    else:
                        event.app.exit(result=False)
                    return

                if self.current_step == "api_key_check":
                    if val == "use_existing":
                        self.state.credentials_configured = True
                        if self._provider_uses_freeform_model(self.state.provider):
                            self.current_step = "model_input"
                        else:
                            self.current_step = "model"
                        self.update_step_data()
                    elif val == "replace":
                        self.current_step = "api_key_input"
                        self.update_step_data()
                    elif val == "skip":
                        self.state.credentials_configured = False
                        if self._provider_uses_freeform_model(self.state.provider):
                            self.current_step = "model_input"
                        else:
                            self.current_step = "model"
                        self.update_step_data()
                    return

                if self.current_step == "google_oauth_adc_check":
                    if val == "retry":
                        self.update_step_data()
                    elif val == "back":
                        self.back_step()
                    elif val == "continue" and self.google_oauth_ready:
                        self.state.credentials_configured = True
                        self.next_step()
                    return

                if self.current_step == "optional_api_key_choice":
                    if val == "set_key":
                        self.current_step = "api_key_input"
                    else:
                        self.state.credentials_configured = False
                        self.current_step = "model_input"
                    self.update_step_data()
                    return

                setattr(self.state, self.current_step, val)
                self.next_step()
            else:
                # Input step
                if self.current_step == "api_key_input":
                    key_name = self._default_key_name(self.state.provider)
                    if self.input_value.strip():
                        self.temp_secrets[key_name] = self.input_value.strip()
                        self.state.credentials_configured = True
                    else:
                        self.state.credentials_configured = False
                    self.next_step()
                elif self.current_step == "research_api_key_input":
                    if self.input_value.strip():
                        key_name = "PERPLEXITY_API_KEY" if self.state.research_provider == "legacy_perplexity" else "ATLAS_RESEARCH_API_KEY"
                        self.temp_secrets[key_name] = self.input_value.strip()
                    self.next_step()
                elif self.current_step == "custom_endpoint":
                    endpoint = self.input_value.strip()
                    if self.state.provider in ("openai-compatible", "custom") and not endpoint:
                        self.title = (
                            f"{self.state.provider} requires a BASE URL.\n"
                            "Enter BASE URL:"
                        )
                        return
                    self.state.custom_endpoint = endpoint
                    if self.state.provider == "lmstudio" and not self.state.custom_endpoint:
                        self.state.custom_endpoint = "http://localhost:1234/v1"
                    self.next_step()
                elif self.current_step == "model_input":
                    model_id = self.input_value.strip()
                    if not model_id:
                        profile = self._provider_profile()
                        model_id = profile.default_model if profile else ""
                    if not model_id:
                        self.title = "Model ID is required."
                        return
                    self.state.model = model_id
                    self.next_step()
                else:
                    setattr(self.state, self.current_step, self.input_value)
                    self.next_step()

        @kb.add("backspace")
        def _(event):
            if not self.choices:
                if self.input_value:
                    self.input_value = self.input_value[:-1]
                else:
                    self.back_step()
            else:
                if self.current_step != "setup_mode":
                    self.back_step()

        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            event.app.exit(result=False)

        @kb.add("<any>")
        def _(event):
            if not self.choices:
                for char in event.data:
                    if char.isprintable():
                        self.input_value += char

        app = Application(
            layout=Layout(
                Window(
                    content=FormattedTextControl(
                        lambda: render_wizard_screen(
                            self.state,
                            self.current_step,
                            self.choices,
                            self.current_index,
                            self.input_value,
                            self.title,
                            is_password=False,
                        )
                    )
                )
            ),
            key_bindings=kb,
            style=atlas_theme,
            full_screen=True,
        )
        return app.run()
