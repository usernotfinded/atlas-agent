from __future__ import annotations


class IBKRStub:
    """IBKR placeholder only. No fake live implementation is provided."""

    def __getattr__(self, name: str):
        raise NotImplementedError("IBKR support requires a future reviewed adapter")

