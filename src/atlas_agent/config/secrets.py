# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    config/secrets.py
# PURPOSE: The only module that reads or writes credentials. Secrets live in
#          .env.atlas (0600), never in config.toml, so that the config file stays
#          safe to commit, share and print.
# DEPS:    python-dotenv (loading), atlas_agent.config.paths (file location)
# ==============================================================================

# --- IMPORTS ---
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from atlas_agent.config.paths import get_env_atlas_path


# --- ERRORS ---

class InvalidSecretValueError(ValueError):
    """Raised when a secret value cannot be safely stored in .env.atlas."""


# --- CONFIGURATIONS & CONSTANTS ---

# Substring match, not equality: this is the oracle the redaction engine consults
# too, so it errs towards over-classifying. A false positive costs a redacted log
# line; a false negative leaks a key.
SECRET_KEYWORDS = {
    "api_key", "token", "secret", "password", "authorization",
    "bearer", "cookie", "private_key", "credentials", "apca_api_key_id", "apca_api_secret_key"
}


# ==============================================================================
# KEY CLASSIFICATION
# ==============================================================================

def is_secret_key(key: str) -> bool:
    """Check if a key looks like a secret."""
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in SECRET_KEYWORDS)

def canonical_env_var(dotted_path: str) -> str:
    """Map a dotted config path to a canonical environment variable name."""
    parts = dotted_path.upper().split(".")
    # Try to extract meaningful prefixes, e.g., providers.openrouter.api_key -> OPENROUTER_API_KEY
    if len(parts) >= 3 and parts[0] == "PROVIDERS":
        provider = parts[1]
        suffix = "_".join(parts[2:])
        # simplify common cases
        if suffix == "API_KEY" or suffix == "TOKEN":
            return f"{provider}_API_KEY"
        return f"{provider}_{suffix}"

    if len(parts) >= 2 and parts[0] == "BROKER":
        # e.g., broker.apca_api_key_id -> APCA_API_KEY_ID
        return "_".join(parts[1:])

    return "_".join(parts)

# ==============================================================================
# SECRET LIFECYCLE (LOAD / SET / UNSET / GET)
# ==============================================================================

def load_atlas_secrets() -> None:
    """Load secrets from .env.atlas into environment. Process env wins."""
    env_path = get_env_atlas_path()
    try:
        if env_path.exists():
            # override=False ensures process environment variables take precedence
            load_dotenv(env_path, override=False)
    except PermissionError:
        # Sandbox/local environments may restrict access to user-global secrets
        pass

    # Every path that changes the set of live secrets must re-arm the redaction
    # engine: it redacts by literal value match against a snapshot of the env, and
    # a secret loaded after that snapshot would print in the clear.
    # Imported lazily to keep the config layer importable without the redaction
    # module, which imports back into config.secrets (circular at module scope).
    try:
        from atlas_agent.redaction import refresh_redaction_secrets
        refresh_redaction_secrets()
    except ImportError:
        pass

def set_secret(key: str, value: str) -> None:
    """Write a secret to .env.atlas."""
    # Validate before touching the file: a malformed key or a value with a newline
    # would corrupt the .env format and silently swallow every line after it.
    _validate_secret_key(key)
    _validate_secret_value(value)
    env_path = get_env_atlas_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # 0600 is re-asserted on every write, not just at creation: the file may have
    # been created by an earlier version, or had its mode widened by a careless
    # `chmod -R`. Cheap to enforce, expensive to get wrong.
    if not env_path.exists():
        env_path.touch(mode=0o600)
    else:
        env_path.chmod(0o600)

    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    # Rewrite in place if the key is already there, so repeated `atlas config set`
    # calls update the entry instead of stacking duplicates that shadow each other.
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}")

    # Ensure trailing newline
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Do not clobber a value the process was launched with: env wins over file, and
    # load_atlas_secrets() relies on that same precedence (override=False).
    if key not in os.environ:
        os.environ[key] = value

    try:
        from atlas_agent.redaction import refresh_redaction_secrets
        refresh_redaction_secrets()
    except ImportError:
        pass

# --- Input validation ---

def _validate_secret_key(key: str) -> None:
    # Shell-identifier grammar. Anything else could not be exported as an env var,
    # and a key containing `=` or a newline would let a caller inject extra lines
    # into .env.atlas.
    import re
    if not isinstance(key, str) or not re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        raise ValueError(f"Invalid secret key name: {key}")

def _validate_secret_value(value: str) -> None:
    # The .env format is line-oriented and has no escaping: an embedded newline
    # would end the assignment early and turn the remainder into a rogue entry.
    if not isinstance(value, str):
        raise InvalidSecretValueError("Secret values must be single-line text.")
    if "\n" in value or "\r" in value or "\0" in value:
        raise InvalidSecretValueError("Secret values must be single-line text.")

def unset_secret(key: str) -> None:
    """Remove a secret from .env.atlas."""
    env_path = get_env_atlas_path()
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = [line for line in lines if not line.strip().startswith(f"{key}=")]

    if len(lines) != len(new_lines):
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        if key in os.environ:
            del os.environ[key]

def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret from environment (which includes .env.atlas)."""
    return os.getenv(key, default)

def get_secret_status(key: str) -> str:
    """Return a redacted status string for a secret key without exposing the value."""
    val = get_secret(key)
    if val is None:
        return "<Not Set>"
    return redact_value(val)

def redact_value(value: str) -> str:
    """Redact a sensitive value."""
    if value is None:
        return "None"
    if value == "":
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
