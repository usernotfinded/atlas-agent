# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/config.py
# PURPOSE: CLI handler for `atlas config` — get, set and unset settings. Routes
#          secrets to .env.atlas and everything else to config.toml, so a user who
#          types a key into `atlas config set` does not commit it by accident.
# DEPS:    atlas_agent.config (the routing lives there, not here)
# ==============================================================================

"""CLI handler for `atlas config`."""

# --- IMPORTS ---
from __future__ import annotations

import os
import shlex
import sys

from atlas_agent.cli_context import CLIContext


def handle_config(context: CLIContext) -> int | None:
    args = context.args
    import json
    config = context.config
    from atlas_agent.cli_io import emit_cli_error
    from atlas_agent.cli_io import emit_cli_success
    from atlas_agent.config.errors import AtlasConfigError
    from atlas_agent.cli import (
        _emit_config_error,
        subprocess,
    )

    if args.command == "config":
        from atlas_agent.config import (
            get_config, get_raw_config, get_raw_value, set_raw_value, unset_raw_value,
            get_secret_status, set_secret, unset_secret, is_secret_key,
            migrate_legacy_config
        )
        from atlas_agent.config.secrets import InvalidSecretValueError, canonical_env_var
        from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path
        import json

        if args.config_command == "paths":
            print(f"Config TOML: {get_config_toml_path()}")
            print(f"Secrets ENV: {get_env_atlas_path()}")
            return 0

        if args.config_command == "show":
            if getattr(args, "effective", False):
                try:
                    config = get_config()
                except AtlasConfigError as exc:
                    return _emit_config_error(exc)
                payload = config.model_dump(mode="json")
                def redact_secrets_in_dict(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            redact_secrets_in_dict(v)
                        elif isinstance(k, str) and is_secret_key(k):
                            d[k] = "[REDACTED]"
                redact_secrets_in_dict(payload)
                print(json.dumps(payload, indent=2))
            else:
                try:
                    raw = get_raw_config()
                except AtlasConfigError as exc:
                    return _emit_config_error(exc)
                import tomlkit
                def redact_recursive(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            redact_recursive(v)
                        elif isinstance(k, str) and is_secret_key(k):
                            d[k] = "[REDACTED]"
                redacted_raw = tomlkit.parse(tomlkit.dumps(raw))
                redact_recursive(redacted_raw)
                print(tomlkit.dumps(redacted_raw))
            return 0

        if args.config_command == "get":
            if is_secret_key(args.key):
                env_var = canonical_env_var(args.key)
                print(get_secret_status(env_var))
                return 0

            if getattr(args, "effective", False):
                try:
                    config = get_config()
                except AtlasConfigError as exc:
                    return _emit_config_error(exc)
                val = config.model_dump(mode="json")
                try:
                    for p in args.key.split("."):
                        val = val[p]
                    print(val)
                except (KeyError, TypeError):
                    print(f"Key not found: {args.key}")
                    return 1
            else:
                val = get_raw_value(args.key)
                if val is None:
                    print(f"Key not found: {args.key}")
                    return 1
                print(val)
            return 0

        if args.config_command == "set":
            if args.key == "model.default":
                args.key = "model.model"
            if is_secret_key(args.key):
                env_var = canonical_env_var(args.key)
                try:
                    set_secret(env_var, args.value)
                except InvalidSecretValueError as exc:
                    print(str(exc))
                    return 2
                print(f"Updated secret {env_var} in .env.atlas")
            else:
                set_raw_value(args.key, args.value)
                print(f"Updated {args.key} in config.toml")
            return 0

        if args.config_command == "unset":
            if is_secret_key(args.key):
                env_var = canonical_env_var(args.key)
                unset_secret(env_var)
                print(f"Unset secret {env_var}")
            else:
                unset_raw_value(args.key)
                print(f"Unset {args.key}")
            return 0

        if args.config_command == "migrate":
            if migrate_legacy_config():
                print("Successfully migrated legacy config.")
            else:
                print("No legacy config found or migration failed.")
            return 0

        if args.config_command == "doctor":
            from atlas_agent.providers.catalog import get_provider_profile, normalize_provider_id
            from atlas_agent.providers.runtime import resolve_runtime_provider
            try:
                config = get_config()
            except AtlasConfigError as exc:
                return _emit_config_error(exc)
            canonical = normalize_provider_id(config.model.provider or "")
            profile = get_provider_profile(canonical)
            runtime = resolve_runtime_provider(config)
            print("Config Doctor")
            print(f"provider: {config.model.provider}")
            print(f"model: {config.model.model}")

            if profile is None:
                print(f"API key: unknown provider '{canonical}'")
            elif not profile.key_required:
                print("API key: not required for this provider")
            else:
                key_source = runtime["api_key_source"]
                env_var_used = runtime["api_key_env_var_used"]
                if key_source in ("process_env", "env_atlas"):
                    print(f"API key: configured/redacted ({env_var_used})")
                else:
                    expected_vars = ", ".join(profile.env_precedence)
                    print(f"API key: missing (expected: {expected_vars})")

                # Warn about ignored keys from other providers
                other_keys_found = []
                for other_p in (get_provider_profile(p) for p in ["openrouter", "anthropic", "openai", "deepseek"]):
                    if other_p and other_p.id != canonical:
                        for var in other_p.env_precedence:
                            if os.getenv(var):
                                other_keys_found.append(var)
                if other_keys_found:
                    print(f"Note: other provider keys detected but ignored: {', '.join(other_keys_found)}")

                # Gemini-specific warning
                if canonical == "google" and runtime.get("warnings"):
                    for w in runtime["warnings"]:
                        print(f"Warning: {w}")

            print(f"live trading {'enabled' if config.enable_live_trading else 'disabled unless explicitly enabled'}")
            print(f"raw prompt logging: {'enabled (redacted)' if config.audit.log_raw_prompts else 'disabled'}")
            print(f"provider text logging: {'enabled (redacted)' if config.audit.log_provider_text else 'disabled'}")
            return 0

        if args.config_command == "edit":
            path = get_config_toml_path()
            editor = os.getenv("EDITOR", "vim")
            subprocess.run(shlex.split(editor) + [str(path)], check=False)
            return 0

        if args.config_command == "check":
            try:
                config = get_config()
                payload = config.model_dump(mode="json")
                def redact_secrets_in_dict(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            redact_secrets_in_dict(v)
                        elif isinstance(k, str) and is_secret_key(k):
                            d[k] = "[REDACTED]"
                redact_secrets_in_dict(payload)
            except AtlasConfigError:
                if getattr(args, "json", False):
                    return emit_cli_error(
                        "atlas config check",
                        code="config_load_failed",
                        message="Configuration check failed.",
                    )
                return _emit_config_error(None)
            except Exception:
                if getattr(args, "json", False):
                    return emit_cli_error(
                        "atlas config check",
                        code="config_check_failed",
                        message="Configuration check failed.",
                    )
                print("Configuration check failed.", file=sys.stderr)
                return 1
            if getattr(args, "json", False):
                return emit_cli_success("atlas config check", payload)
            print("Config is valid.")
            return 0
    return None

