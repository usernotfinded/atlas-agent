# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scheduler/cron.py
# PURPOSE: Suggests a crontab line for a routine. A hint printed for the user to
#          copy — this module never installs a cron job itself.
# DEPS:    none
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations


# ==============================================================================
# CRON HINT
# ==============================================================================

def cron_hint(routine: str) -> str:
    # `--mode paper` is hardcoded into the suggestion. An unattended schedule is the
    # last place to default to live trading, and a user who wants that must type it
    # themselves rather than paste it from us.
    return f"0 9 * * 1-5 atlas scheduler run --routine {routine} --mode paper"

