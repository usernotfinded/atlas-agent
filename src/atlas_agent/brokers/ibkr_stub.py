# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    brokers/ibkr_stub.py
# PURPOSE: A placeholder that refuses to do anything. IBKR is not supported, and
#          this class exists to make that fact LOUD rather than let a half-written
#          adapter quietly reach a real account.
# DEPS:    none
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations


# ==============================================================================
# IBKR PLACEHOLDER
# ==============================================================================

class IBKRStub:
    """IBKR placeholder only. No fake live implementation is provided."""

    # __getattr__ rather than individual stub methods: this way EVERY attribute access
    # raises, including ones added to the Broker protocol later. A stub that silently
    # grows a hole as the interface evolves is worse than no stub at all.
    def __getattr__(self, name: str):
        raise NotImplementedError("IBKR support requires a future reviewed adapter")

