#!/usr/bin/env python3
"""Validate .env.example files: empty secrets, safe defaults, no fake credentials."""

import sys
from pathlib import Path

# Keys whose names contain these substrings must have empty values in committed templates.
_SECRET_NAME_FRAGMENTS = ["API_KEY", "SECRET", "TOKEN", "PASSWORD", "WEBHOOK"]

# Explicitly blocked placeholder strings (case-insensitive exact match after strip).
_BLOCKED_PLACEHOLDERS = {
    "YOUR_API_KEY_HERE",
    "TEST_API_KEY",
    "test_api_key",
}

# Blocked prefixes (case-insensitive).
_BLOCKED_PREFIXES = ["sk-", "bearer "]

# Required safety defaults.
_SAFETY_DEFAULTS = {
    "ENABLE_LIVE_TRADING": "false",
    "TRADING_MODE": "paper",
    "REQUIRE_ORDER_APPROVAL": "true",
    "ALLOW_LEVERAGE": "false",
    "KILL_SWITCH_ENABLED": "false",
    "ORDER_APPROVAL_MODE": "manual_live",
}

# Keys allowed to have non-empty values (non-secret defaults).
_ALLOWED_NON_EMPTY = {
    "TRADING_MODE",
    "ENABLE_LIVE_TRADING",
    "LIVE_BROKER",
    "ORDER_APPROVAL_MODE",
    "REQUIRE_ORDER_APPROVAL",
    "MAX_DAILY_LOSS",
    "MAX_POSITION_SIZE",
    "MAX_TRADES_PER_DAY",
    "MAX_PORTFOLIO_EXPOSURE",
    "MAX_ORDER_NOTIONAL",
    "MINIMUM_CONFIDENCE",
    "ALLOW_LEVERAGE",
    "KILL_SWITCH_ENABLED",
    "REQUIRE_STOP_LOSS_LIVE",
    "ENFORCE_MARKET_HOURS",
    "SYMBOL_ALLOWLIST",
    "SYMBOL_BLOCKLIST",
    "STARTING_CASH",
    "DEFAULT_SYMBOL",
    "DATA_PATH",
    "MEMORY_DIR",
    "AUDIT_DIR",
    "PENDING_ORDERS_DIR",
    "REPORTS_DIR",
    "ALPACA_BASE_URL",
    "PERPLEXITY_MODEL",
    "CLICKUP_WORKSPACE_ID",
    "CLICKUP_LIST_ID",
    "CLICKUP_TASK_ID",
    "ALLOW_GIT_COMMIT",
    "ALLOW_GIT_PUSH",
    "GIT_COMMIT_AUTHOR_NAME",
    "GIT_COMMIT_AUTHOR_EMAIL",
    "AI_PROVIDER",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_MODEL",
    "LOCAL_COMMAND",
}


def _is_secret_key(name: str) -> bool:
    upper = name.upper()
    return any(frag in upper for frag in _SECRET_NAME_FRAGMENTS)


def _parse_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _check_file(path: Path) -> list[str]:
    errors: list[str] = []
    data = _parse_env_file(path)

    for key, value in data.items():
        # Secret keys must be empty
        if _is_secret_key(key) and value != "":
            errors.append(f"{key}: secret key must be empty (got non-empty value)")

        # Blocked placeholders
        if value.upper() in {p.upper() for p in _BLOCKED_PLACEHOLDERS}:
            errors.append(f"{key}: contains blocked placeholder '{value}'")

        # Blocked prefixes
        lower_val = value.lower()
        for prefix in _BLOCKED_PREFIXES:
            if lower_val.startswith(prefix):
                errors.append(f"{key}: contains blocked prefix '{prefix}'")

        # Non-secret keys that are not allowlisted should also be empty
        # unless they are known safe defaults. This catches unexpected values.
        if value != "" and not _is_secret_key(key) and key not in _ALLOWED_NON_EMPTY:
            errors.append(f"{key}: unexpected non-empty value '{value}' (not in allowlist)")

    # Safety defaults
    for key, expected in _SAFETY_DEFAULTS.items():
        actual = data.get(key)
        if actual is None:
            errors.append(f"{key}: missing required safety default")
        elif actual.lower() != expected.lower():
            errors.append(f"{key}: safety default mismatch (expected '{expected}', got '{actual}')")

    return errors


def main() -> int:
    if len(sys.argv) > 1:
        repo_root = Path(sys.argv[1])
    else:
        repo_root = Path(__file__).resolve().parent.parent

    env_files = [
        repo_root / ".env.example",
        repo_root / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
    ]

    total_errors = 0
    for path in env_files:
        if not path.exists():
            print(f"MISSING: {path.relative_to(repo_root)}")
            total_errors += 1
            continue
        findings = _check_file(path)
        rel = path.relative_to(repo_root)
        for finding in findings:
            print(f"{rel}: {finding}")
            total_errors += 1

    # Parity check: root vs packaged templates (same key/value pairs)
    root_path = repo_root / ".env.example"
    tmpl_paths = [
        repo_root / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
    ]
    if root_path.exists():
        root_data = _parse_env_file(root_path)
        for tmpl_path in tmpl_paths:
            if not tmpl_path.exists():
                continue
            tmpl_data = _parse_env_file(tmpl_path)
            # Check same keys
            root_keys = set(root_data.keys())
            tmpl_keys = set(tmpl_data.keys())
            missing_in_tmpl = root_keys - tmpl_keys
            extra_in_tmpl = tmpl_keys - root_keys
            for k in sorted(missing_in_tmpl):
                print(f"{tmpl_path.relative_to(repo_root)}: missing key '{k}' (present in root .env.example)")
                total_errors += 1
            for k in sorted(extra_in_tmpl):
                print(f"{tmpl_path.relative_to(repo_root)}: extra key '{k}' (not in root .env.example)")
                total_errors += 1
            # Check same values for non-comment keys
            for k in sorted(root_keys & tmpl_keys):
                if root_data[k] != tmpl_data[k]:
                    print(
                        f"{tmpl_path.relative_to(repo_root)}: value mismatch for '{k}' "
                        f"(root='{root_data[k]}', template='{tmpl_data[k]}')"
                    )
                    total_errors += 1

    if total_errors:
        return 1

    print("Env template checks clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
