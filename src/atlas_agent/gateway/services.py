# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    gateway/services.py
# PURPOSE: The service contract the remote gateway (Telegram) is allowed to call.
#          Deliberately narrow: it defines the ceiling on what a chat message can
#          make the agent do.
# DEPS:    stdlib only (Protocol)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# ==============================================================================
# SERVICE RESULT
# ==============================================================================

@dataclass(frozen=True)
class ServiceResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# SERVICE CONTRACT
# ==============================================================================

class AgentService(Protocol):
    async def status(self, actor: str) -> ServiceResult:
        ...

    async def plan(self, actor: str) -> ServiceResult:
        ...

    async def run(self, actor: str, mode: str = "auto") -> ServiceResult:
        ...

    async def learn(self, actor: str) -> ServiceResult:
        ...

    async def reflect(self, actor: str) -> ServiceResult:
        ...

    async def positions(self, actor: str) -> ServiceResult:
        ...

    async def memory_search(self, actor: str, query: str) -> ServiceResult:
        ...

    async def skills(self, actor: str) -> ServiceResult:
        ...


class OrderService(Protocol):
    async def pending(self, actor: str) -> ServiceResult:
        ...

    async def approve(self, actor: str, order_id: str) -> ServiceResult:
        ...

    async def reject(self, actor: str, order_id: str) -> ServiceResult:
        ...


class KillSwitchService(Protocol):
    async def kill(self, actor: str, mode: str = "soft", reason: str = "") -> ServiceResult:
        ...

    async def resume(self, actor: str) -> ServiceResult:
        ...

    async def heartbeat(self, actor: str, source: str = "telegram") -> ServiceResult:
        ...

    async def status(self, actor: str) -> ServiceResult:
        ...


class CommandAuditService(Protocol):
    async def log_command(
        self,
        *,
        chat_id: str,
        command: str,
        outcome: str,
        detail: str = "",
        ts_utc: str | None = None,
    ) -> None:
        ...


class NoopCommandAuditService:
    async def log_command(
        self,
        *,
        chat_id: str,
        command: str,
        outcome: str,
        detail: str = "",
        ts_utc: str | None = None,
    ) -> None:
        return None

