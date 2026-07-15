#!/usr/bin/env bash
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/python_env.sh
# PURPOSE: Provides shell tooling for python env.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


resolve_python_bin() {
    if [ -n "${PYTHON_BIN:-}" ]; then
        printf '%s\n' "$PYTHON_BIN"
        return 0
    fi

    if command -v python3.11 >/dev/null 2>&1; then
        printf '%s\n' "python3.11"
        return 0
    fi

    if command -v python >/dev/null 2>&1; then
        printf '%s\n' "python"
        return 0
    fi

    echo "No Python interpreter found. Install Python >= 3.11 or set PYTHON_BIN." >&2
    return 1
}

require_python_311() {
    local python_bin="$1"
    if ! command -v "$python_bin" >/dev/null 2>&1; then
        printf 'Python interpreter not found: %s. Install Python >= 3.11 or set PYTHON_BIN.\n' "$python_bin" >&2
        return 1
    fi

    "$python_bin" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(f"Python >= 3.11 required, got {sys.version.split()[0]}")
PY
}
