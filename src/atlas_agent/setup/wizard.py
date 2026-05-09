from __future__ import annotations

import sys
from typing import Optional

from atlas_agent.setup.state import WizardState
from atlas_agent.setup.wizard_ui import WizardApplication

def is_interactive() -> bool:
    return sys.stdout.isatty() and sys.stdin.isatty()

def run_wizard(state: WizardState) -> bool:
    if not is_interactive():
        return False
    
    app = WizardApplication(state)
    return app.run()
