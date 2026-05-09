from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass

from atlas_agent.providers.adapters import JSONFallbackAdapter
from atlas_agent.providers.base import BaseAIProvider, ProviderRequest, ProviderResponse
from atlas_agent.tools.spec import LLMResponse, ModelCapabilities, ToolDescription


@dataclass(frozen=True)
class LocalCommandProvider(BaseAIProvider):
    """Legacy compatibility provider for local shell-backed model integrations.

    This adapter is retained for compatibility and is not a first-class v2 provider.
    Future architecture should migrate shell execution to the run_shell_command tool.
    """

    command: str
    timeout_seconds: int = 30
    name: str = "local_command"
    default_model: str | None = None

    def _run(self, prompt_text: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            shlex.split(self.command),
            input=prompt_text,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[ToolDescription],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        del model, temperature
        prompt_lines = [f"SYSTEM:\n{system_prompt}\n"]
        if tools:
            prompt_lines.append(JSONFallbackAdapter.build_fallback_prompt(tools))
            prompt_lines.append("")
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            prompt_lines.append(f"{role.upper()}:\n{content}")

        process = self._run("\n\n".join(prompt_lines).strip())
        raw = {
            "returncode": process.returncode,
            "stderr": process.stderr.strip() or None,
        }
        output_text = process.stdout.strip()
        if tools:
            return JSONFallbackAdapter.normalize(output_text, tools, raw=raw)
        return LLMResponse(
            text=output_text or None,
            tool_calls=[],
            is_final=True,
            raw=raw,
        )

    def summarize(
        self,
        text: str,
        max_tokens: int,
    ) -> str:
        return super().summarize(text=text, max_tokens=max_tokens)

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=32_000,
            supports_native_tools=False,
            supports_json_mode=False,
            supports_streaming=False,
            provider_name=self.name,
            model_name=self.default_model,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        process = self._run(request.user_prompt)
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
