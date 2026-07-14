# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    notifications/telegram_stub.py
# PURPOSE: A Telegram notifier that sends nothing. The real Telegram surface is the
#          control plane in gateway/telegram/ — this is only the outbound-message
#          placeholder.
# DEPS:    none
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations


# ==============================================================================
# TELEGRAM STUB
# ==============================================================================

class TelegramNotifierStub:
    def send(self, message: str) -> dict[str, str]:
        return {"status": "stub", "message": message}

