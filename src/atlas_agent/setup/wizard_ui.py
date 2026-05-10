import os
from typing import List, Tuple, Optional, Any
from pathlib import Path
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.filters import Condition
from atlas_agent.setup.state import WizardState
from atlas_agent.setup.renderer import render_wizard_screen
from atlas_agent.setup.theme import atlas_theme

PROVIDER_KEY_MAP = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compatible": "OPENAI_API_KEY",
    "custom": "CUSTOM_PROVIDER_API_KEY",
}

class WizardApplication:
    def __init__(self, state: WizardState):
        self.state = state
        self.current_step = "setup_mode"
        self.history: List[str] = []
        self.current_index = 0
        self.input_value = ""
        self.choices: List[Tuple[str, str]] = []
        self.title = ""
        self.temp_secrets = {}
        self.update_step_data()

    def update_step_data(self):
        if self.current_step == "setup_mode":
            self.title = "How would you like to set up Atlas Agent?"
            self.choices = [
                ("quick", "Quick setup — provider, model & messaging (recommended)"),
                ("full", "Full setup — configure everything")
            ]
            self.current_index = 0 if self.state.setup_mode == "quick" else 1
        elif self.current_step == "provider":
            self.title = "Select provider:"
            self.choices = [
                ("openrouter", "OpenRouter — 100+ models, pay-per-use"),
                ("anthropic", "Anthropic — Claude models"),
                ("openai_compatible", "OpenAI-compatible endpoint"),
                ("local_command", "Local command provider — legacy compatibility"),
                ("custom", "Custom endpoint"),
                ("null", "Null provider / dry-run"),
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.provider), 0)
        elif self.current_step == "api_key_check":
            key_name = PROVIDER_KEY_MAP.get(self.state.provider)
            self.title = f"API Key Detection: {key_name} detected from environment."
            self.choices = [
                ("use_existing", "Use existing from environment"),
                ("replace", "Replace / Enter manually"),
                ("skip", "Skip for now")
            ]
            self.current_index = 0
        elif self.current_step == "api_key_input":
            key_name = PROVIDER_KEY_MAP.get(self.state.provider)
            self.title = f"Enter {key_name}:"
            self.choices = []
            self.input_value = ""
        elif self.current_step == "custom_endpoint":
            if self.state.provider == "openai_compatible":
                self.title = "Enter OpenAI-compatible BASE URL:"
            else:
                self.title = "Enter Custom Provider BASE URL:"
            self.choices = []
            self.input_value = self.state.custom_endpoint or ""
        elif self.current_step == "model":
            if self.state.provider == "local_command":
                self.title = "WARNING: Local command provider is legacy compatibility only.\nSelect model:"
            else:
                self.title = f"Select model for {self.state.provider}:"
            if self.state.provider == "anthropic":
                self.choices = [("claude-3-5-sonnet-20240620", "Claude 3.5 Sonnet"), ("claude-3-opus-20240229", "Claude 3 Opus")]
            elif self.state.provider in ["openrouter", "openai_compatible", "custom"]:
                self.choices = [("gpt-4o", "GPT-4o"), ("meta-llama/llama-3-70b-instruct", "Llama 3 70B")]
            else:
                self.choices = [("default", "Default Model")]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.model), 0)
        elif self.current_step == "research_provider":
            self.title = "Optional web research provider:"
            self.choices = [
                ("skip", "Skip for now"),
                ("custom", "Custom search/research API"),
                ("local", "Self-hosted/local provider"),
                ("existing", "Existing environment variable"),
                ("legacy_perplexity", "Legacy Perplexity backend"),
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.research_provider), 0)
        elif self.current_step == "research_api_key_input":
            self.title = "Enter ATLAS_RESEARCH_API_KEY (or legacy PERPLEXITY_API_KEY):"
            self.choices = []
            self.input_value = ""
        elif self.current_step == "messaging":
            self.title = "Select messaging integration:"
            self.choices = [
                ("cli", "CLI only"),
                ("telegram", "Telegram (experimental)"),
                ("none", "None")
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.messaging), 0)
        elif self.current_step == "workspace_path":
            self.title = "Workspace:"
            self.choices = []
            self.input_value = self.state.workspace_path
        elif self.current_step == "trust_mode":
            self.title = "Select execution trust mode:"
            self.choices = [
                ("paper", "Paper Trading"),
                ("live", "Live Trading (Requires Approval)")
            ]
            self.current_index = 0 if self.state.trust_mode == "paper" else 1
        elif self.current_step == "broker_mode":
            self.title = "Select broker mode:"
            self.choices = [
                ("paper", "Paper Broker"),
                ("alpaca", "Alpaca"),
                ("binance", "Binance"),
                ("ccxt", "CCXT (Generic)")
            ]
            self.current_index = next((i for i, v in enumerate(self.choices) if v[0] == self.state.broker_mode), 0)
        elif self.current_step == "update_channel":
            self.title = "Select update channel:"
            self.choices = [
                ("stable", "Stable"),
                ("beta", "Beta")
            ]
            self.current_index = 0 if self.state.update_channel == "stable" else 1
        elif self.current_step == "review":
            self.title = "Review your configuration:"
            self.choices = [
                ("save", "Save and exit"),
                ("back", "Back"),
                ("cancel", "Cancel")
            ]
            self.current_index = 0

    def next_step(self):
        self.history.append(self.current_step)
        if self.current_step == "setup_mode":
            self.current_step = "provider"
        elif self.current_step == "provider":
            if self.state.provider == "custom":
                self.current_step = "custom_endpoint"
            elif self.state.provider == "local_command":
                self.current_step = "model"
            elif self.state.provider in PROVIDER_KEY_MAP:
                key_name = PROVIDER_KEY_MAP[self.state.provider]
                if os.getenv(key_name):
                    self.current_step = "api_key_check"
                else:
                    self.current_step = "api_key_input"
            else:
                self.current_step = "model"
        elif self.current_step == "api_key_check":
            pass # result logic is in run()'s kb handler
        elif self.current_step == "api_key_input":
            if self.state.provider == "openai_compatible" and self.history[-2] == "provider":
                self.current_step = "custom_endpoint"
            else:
                self.current_step = "model"
        elif self.current_step == "custom_endpoint":
            if self.state.provider == "custom" and self.history[-2] == "provider":
                key_name = PROVIDER_KEY_MAP[self.state.provider]
                if os.getenv(key_name):
                    self.current_step = "api_key_check"
                else:
                    self.current_step = "api_key_input"
            elif self.state.provider == "openai_compatible" and self.history[-2] == "api_key_input":
                self.current_step = "model"
            else:
                self.current_step = "model"
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
            if self.state.setup_mode == "full":
                self.current_step = "workspace_path"
            else:
                self.current_step = "review"
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
                        if self.state.provider == "openai_compatible" and "custom_endpoint" not in self.history:
                            self.current_step = "custom_endpoint"
                        else:
                            self.current_step = "model"
                        self.update_step_data()
                    elif val == "replace":
                        self.current_step = "api_key_input"
                        self.update_step_data()
                    elif val == "skip":
                        self.state.credentials_configured = False
                        if self.state.provider == "openai_compatible" and "custom_endpoint" not in self.history:
                            self.current_step = "custom_endpoint"
                        else:
                            self.current_step = "model"
                        self.update_step_data()
                    return

                setattr(self.state, self.current_step, val)
                self.next_step()
            else:
                # Input step
                if self.current_step == "api_key_input":
                    key_name = PROVIDER_KEY_MAP.get(self.state.provider)
                    if self.input_value.strip():
                        self.temp_secrets[key_name] = self.input_value.strip()
                        self.state.credentials_configured = True
                    self.next_step()
                elif self.current_step == "research_api_key_input":
                    if self.input_value.strip():
                        key_name = "PERPLEXITY_API_KEY" if self.state.research_provider == "legacy_perplexity" else "ATLAS_RESEARCH_API_KEY"
                        self.temp_secrets[key_name] = self.input_value.strip()
                    self.next_step()
                elif self.current_step == "custom_endpoint":
                    self.state.custom_endpoint = self.input_value.strip()
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
            layout=Layout(Window(content=FormattedTextControl(
                lambda: render_wizard_screen(
                    self.state, self.current_step, self.choices, 
                    self.current_index, self.input_value, self.title,
                    is_password=(self.current_step in ["api_key_input", "research_api_key_input"])
                )
            ))),
            key_bindings=kb,
            style=atlas_theme,
            full_screen=True
        )
        return app.run()
