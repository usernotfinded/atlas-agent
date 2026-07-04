"""CLI handler for `atlas model`."""
from __future__ import annotations

import getpass
import warnings

from atlas_agent.cli_context import CLIContext


def handle_model(context: CLIContext) -> int | None:
    args = context.args
    config = context.config
    from atlas_agent.config.errors import AtlasConfigError
    from atlas_agent.cli import _emit_config_error

    if args.command == "model":
        from atlas_agent.config import get_config, set_raw_value
        from atlas_agent.providers.catalog import (
            infer_google_api_mode,
            list_provider_profiles,
            get_provider_profile,
            normalize_provider_id,
            is_known_model_for_provider,
            provider_allows_custom_model,
            validate_model_for_provider,
        )
        from atlas_agent.providers.runtime import resolve_runtime_provider
        from atlas_agent.config.secrets import InvalidSecretValueError, set_secret
        try:
            config = get_config()
        except AtlasConfigError as exc:
            return _emit_config_error(exc)

        if args.model_command == "providers":
            for profile in list_provider_profiles():
                if not profile.include_in_model_providers_default:
                    continue
                runtime = resolve_runtime_provider(config, profile.id)
                key_status = runtime["api_key_source"]
                if runtime.get("auth_method") == "oauth_adc":
                    key_label = "oauth/adc" if runtime.get("credential_source") != "missing" else "oauth missing"
                elif key_status == "missing" and profile.auth_header_type != "none" and profile.key_required:
                    key_label = "missing"
                elif key_status in ("process_env", "env_atlas"):
                    key_label = "configured"
                else:
                    key_label = "not required"
                print(f"{profile.id:15s}  {profile.label:25s}  key: {key_label:12s}  default: {profile.default_model}")

            if getattr(args, "include_legacy", False):
                print(f"{'local_command':15s}  {'Local command (legacy)':25s}  key: {'not required':12s}  default: {'local_command'}")

            if getattr(args, "include_internal", False):
                print(f"{'null':15s}  {'Null provider / dry-run':25s}  key: {'not required':12s}  default: {'null'}")
            return 0
        if args.model_command == "list":
            provider_filter = getattr(args, "provider", None)
            if provider_filter:
                profile = get_provider_profile(provider_filter)
                if not profile:
                    print(f"Unknown provider: {provider_filter}")
                    return 2
                profiles = [profile]
            else:
                profiles = list_provider_profiles()
            for profile in profiles:
                print(f"{profile.label} ({profile.id})")
                for m in profile.models:
                    rec = "  *" if m.recommended else ""
                    print(f"  {m.id:40s}{rec}")
                if profile.allow_custom_model:
                    print("  Custom model IDs allowed.")
            return 0

        if args.model_command == "current":
            runtime = resolve_runtime_provider(config)
            print(f"provider: {runtime.get('provider_label', runtime['provider'])}")
            print(f"provider_id: {runtime['provider']}")
            print(f"model:    {runtime['model']}")
            print(f"mode:     {runtime.get('mode_label', runtime['api_mode'])}")
            print(f"api_mode: {runtime['api_mode']}")
            print(f"base_url: {runtime['base_url'] or '(default)'}")
            key_source = runtime["api_key_source"]
            env_var = runtime["api_key_env_var_used"]
            if runtime.get("auth_method") == "oauth_adc":
                if runtime.get("credential_source") != "missing":
                    print(f"auth:     OAuth/ADC configured ({runtime['credential_source']})")
                else:
                    print("auth:     OAuth/ADC missing")
            else:
                if key_source == "process_env":
                    print(f"auth:     API key configured ({env_var} from process env)")
                elif key_source == "env_atlas":
                    print(f"auth:     API key configured ({env_var} from .env.atlas)")
                elif key_source == "none":
                    print("auth:     not required")
                else:
                    print("auth:     API key missing")
            for err in runtime.get("errors", []):
                print(f"error:    {err}")
            if runtime.get("warnings"):
                for w in runtime["warnings"]:
                    print(f"warning:  {w}")
            return 0

        if args.model_command == "set":
            # Two-arg form: atlas model set <provider> <model>
            if args.model is not None:
                raw_provider_input = args.model_id.strip()
                provider_id = normalize_provider_id(raw_provider_input)
                model_id = args.model.strip()
            else:
                raw = args.model_id.strip()
                raw_provider_input = ""
                # Support "openrouter:openai/gpt-5.5" or single-argument syntax
                if ":" in raw and "/" in raw:
                    provider_part, model_part = raw.split(":", 1)
                    raw_provider_input = provider_part
                    provider_id = normalize_provider_id(provider_part)
                    model_id = model_part
                elif "/" in raw:
                    provider_part, model_part = raw.split("/", 1)
                    raw_provider_input = provider_part
                    provider_id = normalize_provider_id(provider_part)
                    model_id = raw  # Keep full ID for openrouter-style models
                    # For non-openrouter providers, use just the model_part
                    profile = get_provider_profile(provider_id)
                    if profile and profile.id != "openrouter":
                        model_id = model_part
                else:
                    # No provider prefix; use current provider
                    raw_provider_input = config.model.provider or "openai"
                    provider_id = normalize_provider_id(config.model.provider or "openai")
                    model_id = raw

            profile = get_provider_profile(provider_id)
            if not profile:
                print(f"Warning: unknown provider '{provider_id}'.")
            else:
                provider_id = profile.id  # canonical
                valid_pair, validation_error = validate_model_for_provider(provider_id, model_id)
                if not valid_pair:
                    print(f"Error: {validation_error}")
                    return 2
                if (
                    not provider_allows_custom_model(provider_id)
                    and not is_known_model_for_provider(provider_id, model_id)
                ):
                    print(f"Warning: '{model_id}' is not in the curated catalog for {provider_id}.")
                    print("Proceeding because this may be a newer model ID.")

            set_raw_value("model.provider", provider_id)
            set_raw_value("model.model", model_id)
            if provider_id == "google":
                inferred_google_mode = infer_google_api_mode(raw_provider_input)
                if inferred_google_mode:
                    set_raw_value("model.google.api_mode", inferred_google_mode)
            print(f"Model set to {provider_id}/{model_id}")
            return 0

        if args.model_command == "configure":
            profiles = list_provider_profiles()
            print("Select a provider:")
            for i, profile in enumerate(profiles, 1):
                print(f"  {i}. {profile.label} ({profile.id})")
            try:
                choice = input("Enter number (or provider id): ").strip()
            except (EOFError, OSError):
                print("Non-interactive mode. Use `atlas model set <provider>/<model>` instead.")
                return 2
            # Allow entering provider id directly
            profile = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(profiles):
                    profile = profiles[idx]
            if not profile:
                profile = get_provider_profile(choice)
            if not profile:
                print(f"Unknown provider: {choice}")
                return 2

            # Prompt for API key if needed and missing
            if profile.key_required:
                runtime = resolve_runtime_provider(config, profile.id)
                if runtime["api_key_source"] in ("missing", ""):
                    print(f"{profile.label} requires an API key.")
                    env_var = profile.canonical_env_var if profile.canonical_env_var else f"{profile.id.upper()}_API_KEY"
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", getpass.GetPassWarning)
                            key = getpass.getpass(f"Enter {env_var}: ").strip()
                    except getpass.GetPassWarning:
                        print("Secure hidden input is unavailable in this environment. Use `atlas config set_atlas_secret <key> <value>`.")
                        return 2
                    except (EOFError, OSError):
                        print("Non-interactive mode. Use `atlas config set_atlas_secret <key> <value>`.")
                        return 2
                    if key:
                        try:
                            set_secret(env_var, key)
                        except InvalidSecretValueError as exc:
                            print(str(exc))
                            return 2
                        print(f"Saved {env_var} to .env.atlas")

            # Select model
            print(f"Select a model for {profile.label}:")
            for i, m in enumerate(profile.models, 1):
                rec = "  *" if m.recommended else ""
                print(f"  {i}. {m.id:40s}{rec}")
            try:
                mchoice = input("Enter number (or model id, or press Enter for default): ").strip()
            except (EOFError, OSError):
                print("Non-interactive mode. Use `atlas model set <provider>/<model>`.")
                return 2
            model_id = profile.default_model
            if mchoice:
                if mchoice.isdigit():
                    idx = int(mchoice) - 1
                    if 0 <= idx < len(profile.models):
                        model_id = profile.models[idx].id
                else:
                    model_id = mchoice

            set_raw_value("model.provider", profile.id)
            set_raw_value("model.model", model_id)
            print(f"Configured {profile.id}/{model_id}")
            return 0
    return None

