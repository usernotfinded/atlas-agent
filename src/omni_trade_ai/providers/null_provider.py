from __future__ import annotations

from omni_trade_ai.providers.base import ProviderRequest, ProviderResponse


class NullProvider:
    name = "null"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        payload = {
            "action": "hold",
            "symbol": request.metadata.get("symbol", "UNKNOWN"),
            "confidence": 0.0,
            "time_horizon": "intraday",
            "reasoning_summary": "NullProvider deterministic hold.",
            "risk_notes": "No model call was made.",
            "proposed_order": None,
        }
        return ProviderResponse(text=str(payload), parsed_json=payload)

