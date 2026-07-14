# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    notifications/slack_stub.py
# PURPOSE: A Slack notifier that sends nothing. Used where the interface is needed
#          but delivery is not — so a misconfiguration results in silence, never in
#          an unintended post to a real channel.
# DEPS:    none
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations


# ==============================================================================
# SLACK STUB
# ==============================================================================

class SlackNotifierStub:
    def send(self, message: str) -> dict[str, str]:
        return {"status": "stub", "message": message}

