import os
import re
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv, set_key

from atlas_agent.config.paths import get_env_atlas_path

SECRET_KEYWORDS = {
    "api_key", "token", "secret", "password", "authorization", 
    "bearer", "cookie", "private_key", "credentials"
}

def is_secret_key(key: str) -> bool:
    """Check if a key looks like a secret."""
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in SECRET_KEYWORDS)

def load_atlas_secrets() -> None:
    """Load secrets from .env.atlas into environment."""
    env_path = get_env_atlas_path()
    if env_path.exists():
        load_dotenv(env_path)

def set_atlas_secret(key: str, value: str) -> None:
    """Write a secret to .env.atlas."""
    env_path = get_env_atlas_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure file permissions are restricted (user-only read/write)
    if not env_path.exists():
        env_path.touch(mode=0o600)
    else:
        env_path.chmod(0o600)
        
    # Use a simple write instead of set_key to avoid unwanted quotes if desired,
    # but set_key is safer for preserving other values.
    # However, tests expect no quotes.
    # We will implement a simple parser/writer to maintain compatibility.
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    
    if not found:
        lines.append(f"{key}={value}")
    
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret from environment (which includes .env.atlas)."""
    return os.getenv(key, default)

def redact_value(value: str) -> str:
    """Redact a sensitive value."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
