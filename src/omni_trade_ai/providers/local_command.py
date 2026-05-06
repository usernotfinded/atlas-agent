from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass

from omni_trade_ai.providers.base import ProviderRequest, ProviderResponse


@dataclass(frozen=True)
class LocalCommandProvider:
    command: str
    timeout_seconds: int = 30
    name: str = "local_command"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        process = subprocess.run(
            shlex.split(self.command),
            input=request.user_prompt,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        parsed = None
        try:
            parsed = json.loads(process.stdout)
        except json.JSONDecodeError:
            parsed = None
        return ProviderResponse(
            text=process.stdout.strip(),
            parsed_json=parsed,
            raw_response={"returncode": process.returncode},
            finish_reason="stop" if process.returncode == 0 else "error",
        )

