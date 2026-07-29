# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    setup/state.py
# PURPOSE: What the setup wizard has collected so far. Every default below is the
#          SAFE one — a user who accepts every default ends up in paper mode with no
#          broker, which is exactly where a new user should land.
# DEPS:    providers.catalog (model validation, imported lazily)
# ==============================================================================

# --- IMPORTS ---
from dataclasses import dataclass, asdict
from typing import Optional
import json
from pathlib import Path


# ==============================================================================
# WIZARD STATE
# ==============================================================================

@dataclass
class WizardState:
    setup_mode: str = "quick" # quick or full
    provider: str = ""
    model: str = ""
    google_api_mode: str = "native" # native | openai_compatible
    google_auth_method: str = "api_key" # api_key | oauth_adc
    custom_endpoint: Optional[str] = None
    research_provider: str = "skip"
    messaging: str = "cli"
    workspace_path: str = "."
    # Both default to paper, and the wizard cannot be click-through'd into live: the
    # dangerous option always requires an explicit choice.
    trust_mode: str = "paper"
    broker_mode: str = "paper"
    update_channel: str = "stable"
    credentials_configured: bool = False

    def _provider_model_error(self) -> str | None:
        from atlas_agent.providers.catalog import normalize_provider_id, validate_model_for_provider

        canonical_provider = normalize_provider_id(self.provider)
        ok, error = validate_model_for_provider(canonical_provider, self.model)
        if ok:
            return None
        return error

    @property
    def is_complete(self) -> bool:
        from atlas_agent.providers.catalog import get_provider_profile, normalize_provider_id

        mandatory_fields = [
            "provider", "model", "messaging", 
            "workspace_path", "trust_mode", 
            "broker_mode", "update_channel"
        ]
        if not all(bool(getattr(self, field)) for field in mandatory_fields):
            return False
            
        # Provider specific credential check
        if self.provider in ["null", "local_command"]:
            return True

        canonical_provider = normalize_provider_id(self.provider)
        profile_error = self._provider_model_error()
        if profile_error:
            return False

        profile = get_provider_profile(canonical_provider)
        if profile and not profile.key_required:
            return True

        if canonical_provider == "google" and self.google_auth_method == "oauth_adc":
            return self.credentials_configured

        return self.credentials_configured

    def to_dict(self) -> dict:
        return asdict(self)
        
    def save(self, path: Optional[Path] = None) -> None:
        from atlas_agent.config import set_raw_value, unset_raw_value
        from atlas_agent.providers.catalog import default_model_for_provider, normalize_provider_id

        # Ensure the local workspace config dir exists so config writes do not
        # fall back to $HOME/.atlas outside the active workspace.
        Path(".atlas").mkdir(parents=True, exist_ok=True)
        
        # New config system
        set_raw_value("trading_mode", self.trust_mode)
        canonical_provider = normalize_provider_id(self.provider)
        if not self.model:
            self.model = default_model_for_provider(canonical_provider)
        model_error = self._provider_model_error()
        if model_error:
            raise ValueError(model_error)

        set_raw_value("model.provider", canonical_provider)
        set_raw_value("model.model", self.model)
        if canonical_provider == "google":
            set_raw_value("model.google.api_mode", self.google_api_mode)
            set_raw_value("model.google.auth_method", self.google_auth_method)
            unset_raw_value("model.base_url")
            if self.custom_endpoint:
                set_raw_value("model.google.base_url", self.custom_endpoint)
            else:
                unset_raw_value("model.google.base_url")
        else:
            unset_raw_value("model.google.api_mode")
            unset_raw_value("model.google.auth_method")
            unset_raw_value("model.google.base_url")
            if self.custom_endpoint:
                set_raw_value("model.base_url", self.custom_endpoint)
            else:
                unset_raw_value("model.base_url")
        
        set_raw_value("broker.provider", self.broker_mode)
        # `update_channel` is deliberately not written to config. It holds "stable"
        # or "beta" — a release channel — and used to be written to
        # `update.auto_check`, which is a check *frequency* documented as
        # "daily", "weekly", or "never". Running the wizard therefore left
        # `update.auto_check = "stable"` in config.toml.
        #
        # Nothing read it: that write was the only reference to the field in the
        # whole codebase, and the update manager keeps its schedule in its own
        # state file, which is why `atlas update status` reported "off" rather
        # than "stable". So this corrupted a typed field without any visible
        # effect, which is the kind that survives longest.
        #
        # There is no release-channel setting to write it to instead — `update/`
        # has no channel concept at all. The wizard still records the answer in
        # its own state file; giving it a home in the runtime config would mean
        # implementing channel support, not moving a line.
        
        if self.messaging == "cli":
            set_raw_value("safety.order_approval_mode", "manual_live")
        
        set_raw_value("workspace_root", self.workspace_path)

        # Legacy backward compatibility for tests
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)

            
    @classmethod
    def load(cls, path: Path) -> "WizardState":
        if not path.exists():
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Filter to only valid keys for forward compatibility
            valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            return cls(**filtered_data)
        except (json.JSONDecodeError, OSError):
            return cls()
