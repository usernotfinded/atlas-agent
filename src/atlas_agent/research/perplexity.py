from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

from atlas_agent.research.research_report import ResearchReport


class ResearchConfigurationError(RuntimeError):
    pass


HttpPost = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class PerplexityResearchProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        http_post: HttpPost | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ATLAS_RESEARCH_API_KEY") or os.getenv("RESEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
        self.model = model or os.getenv("RESEARCH_MODEL") or os.getenv("PERPLEXITY_MODEL", "sonar-pro")
        self.http_post = http_post or _default_http_post

    def research_market(self, symbol: str) -> ResearchReport:
        if not self.api_key:
            raise ResearchConfigurationError("ATLAS_RESEARCH_API_KEY is not configured")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Summarize market catalysts. Do not make return claims.",
                },
                {
                    "role": "user",
                    "content": f"Research current market context for {symbol}.",
                },
            ],
        }
        raw = self.http_post(
            "https://api.perplexity.ai/chat/completions",
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload,
        )
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = tuple(str(item) for item in raw.get("citations", ()))
        return ResearchReport(
            symbol=symbol.upper(),
            provider="perplexity",
            summary=text or "No research summary returned.",
            citations=citations,
        )


def _default_http_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

