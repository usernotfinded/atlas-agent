from dataclasses import dataclass, asdict
from typing import Optional
import json
from pathlib import Path

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
    trust_mode: str = "paper"
    broker_mode: str = "paper"
    update_channel: str = "stable"
    credentials_configured: bool = False

    @property
    def is_complete(self) -> bool:
        from atlas_agent.providers.catalog import get_provider_profile

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

        profile = get_provider_profile(self.provider)
        if profile and not profile.key_required:
            return True

        if self.provider == "google" and self.google_auth_method == "oauth_adc":
            return self.credentials_configured

        return self.credentials_configured

    def to_dict(self) -> dict:
        return asdict(self)
        
    def save(self, path: Optional[Path] = None) -> None:
        from atlas_agent.config import set_raw_value
        from atlas_agent.providers.catalog import normalize_provider_id

        # Ensure the local workspace config dir exists so config writes do not
        # fall back to $HOME/.atlas outside the active workspace.
        Path(".atlas").mkdir(parents=True, exist_ok=True)
        
        # New config system
        set_raw_value("trading_mode", self.trust_mode)
        canonical_provider = normalize_provider_id(self.provider)
        set_raw_value("model.provider", canonical_provider)
        set_raw_value("model.model", self.model)
        if canonical_provider == "google":
            set_raw_value("model.google.api_mode", self.google_api_mode)
            set_raw_value("model.google.auth_method", self.google_auth_method)
        if self.custom_endpoint:
            if canonical_provider == "google":
                set_raw_value("model.google.base_url", self.custom_endpoint)
            else:
                set_raw_value("model.base_url", self.custom_endpoint)
        
        set_raw_value("broker.provider", self.broker_mode)
        set_raw_value("update.auto_check", self.update_channel)
        
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
