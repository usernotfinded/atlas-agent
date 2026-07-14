# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    setup/wizard.py
# PURPOSE: Entry point for the interactive setup wizard.
# DEPS:    setup.state, setup.wizard_ui
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import sys
from typing import Optional

from atlas_agent.setup.state import WizardState
from atlas_agent.setup.wizard_ui import WizardApplication


# ==============================================================================
# WIZARD ENTRY POINT
# ==============================================================================

def is_interactive() -> bool:
    # BOTH streams must be a TTY. Checking only stdout would let a piped-in script
    # reach a prompt that then blocks forever waiting on input nobody will type.
    return sys.stdout.isatty() and sys.stdin.isatty()

def run_wizard(state: WizardState) -> bool:
    # Returns False rather than prompting when there is no terminal. The wizard is how
    # credentials and trading mode get set, so it must never run half-blind in CI, in a
    # cron job or under a pipe.
    if not is_interactive():
        return False

    app = WizardApplication(state)
    return app.run()
