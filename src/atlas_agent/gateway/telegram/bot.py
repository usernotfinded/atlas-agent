from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from atlas_agent.gateway.services import (
    AgentService,
    CommandAuditService,
    KillSwitchService,
    NoopCommandAuditService,
    OrderService,
    ServiceResult,
)
from atlas_agent.gateway.telegram.auth import TelegramAuth
from atlas_agent.gateway.telegram.ratelimit import TelegramRateLimiter
from atlas_agent.gateway.telegram.sanitize import sanitize_output


TIMEOUT_MESSAGE = "operazione in corso, ti aggiorno con /pending"
UNAUTHORIZED_MESSAGE = "Accesso non autorizzato."
RATE_LIMIT_MESSAGE = "Troppi comandi, riprova più tardi."

MONEY_TOUCHING_ACTIONS = {
    "approve",
    "kill",
    "resume",
    "run_live",
}


@dataclass(frozen=True)
class TelegramBotConfig:
    command_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")


@dataclass(frozen=True)
class CommandContext:
    chat_id: str
    actor: str
    raw_text: str
    command: str
    args: tuple[str, ...]


class TelegramCommandBot:
    def __init__(
        self,
        *,
        auth: TelegramAuth,
        rate_limiter: TelegramRateLimiter,
        agent_service: AgentService,
        order_service: OrderService,
        kill_switch_service: KillSwitchService,
        audit_service: CommandAuditService | None = None,
        config: TelegramBotConfig | None = None,
    ) -> None:
        self.auth = auth
        self.rate_limiter = rate_limiter
        self.agent_service = agent_service
        self.order_service = order_service
        self.kill_switch_service = kill_switch_service
        self.audit_service = audit_service or NoopCommandAuditService()
        self.config = config or TelegramBotConfig()

    async def handle_update(self, update: Any) -> str:
        chat = getattr(update, "effective_chat", None)
        user = getattr(update, "effective_user", None)
        message = getattr(update, "effective_message", None) or getattr(update, "message", None)
        text = getattr(message, "text", None)
        if chat is None or text is None:
            return "Comando non valido."
        chat_id = str(getattr(chat, "id", "")).strip()
        actor_id = str(getattr(user, "id", chat_id)).strip()
        return await self.handle_text(chat_id=chat_id, text=text, actor=f"user:{actor_id}")

    async def handle_text(self, *, chat_id: str | int, text: str, actor: str) -> str:
        chat_key = str(chat_id).strip()
        raw_text = text.strip()
        if not raw_text:
            return "Comando non valido."
        if not self.auth.is_authorized(chat_key):
            await self._audit(chat_key, raw_text, "rejected", "unauthorized")
            return UNAUTHORIZED_MESSAGE

        # If a sensitive challenge is pending, treat this message as TOTP code.
        if self.auth.has_pending_challenge(chat_key):
            verification = self.auth.verify_challenge(chat_id=chat_key, code=raw_text)
            if not verification.ok:
                await self._audit(chat_key, raw_text, "rejected", verification.reason)
                return "Codice TOTP non valido o scaduto."
            assert verification.challenge is not None
            response = await self._execute_challenged_action(
                challenge_command=verification.challenge.command,
                payload=verification.challenge.payload,
                chat_id=chat_key,
                actor=actor,
            )
            return response

        ctx = _parse_command(chat_key, actor, raw_text)
        if ctx is None:
            await self._audit(chat_key, raw_text, "rejected", "unknown command")
            return "Comando non supportato."

        money_touching = _is_money_touching(ctx)
        rate = self.rate_limiter.check(chat_key, money_touching=money_touching)
        if not rate.allowed:
            await self._audit(chat_key, ctx.command, "rejected", rate.message)
            return RATE_LIMIT_MESSAGE

        if money_touching:
            self.auth.start_challenge(
                chat_id=chat_key,
                command=ctx.command,
                actor=actor,
                payload={"args": list(ctx.args), "raw_text": ctx.raw_text},
            )
            await self._audit(chat_key, ctx.command, "pending_2fa", "challenge_started")
            return self.auth.confirmation_message()

        return await self._execute_command(ctx)

    async def _execute_challenged_action(
        self,
        *,
        challenge_command: str,
        payload: dict[str, Any],
        chat_id: str,
        actor: str,
    ) -> str:
        args_raw = payload.get("args", [])
        args = tuple(str(item) for item in args_raw if str(item).strip())
        ctx = CommandContext(
            chat_id=chat_id,
            actor=actor,
            raw_text=str(payload.get("raw_text", challenge_command)),
            command=challenge_command,
            args=args,
        )
        return await self._execute_command(ctx)

    async def _execute_command(self, ctx: CommandContext) -> str:
        try:
            response = await self._run_with_timeout(self._dispatch(ctx))
        except Exception as exc:
            await self._audit(ctx.chat_id, ctx.command, "failed", str(exc))
            return "Errore interno durante l'esecuzione del comando."
        await self._audit(
            ctx.chat_id,
            ctx.command,
            "ok",
            "success" if response != TIMEOUT_MESSAGE else "timeout",
        )
        return response

    async def _dispatch(self, ctx: CommandContext) -> str:
        command = ctx.command
        if command == "/status":
            result = await self.agent_service.status(ctx.actor)
            return _format_service_result(result)
        if command == "/plan":
            result = await self.agent_service.plan(ctx.actor)
            return _format_service_result(result)
        if command == "/run":
            mode = _arg_or_default(ctx.args, 0, "auto")
            result = await self.agent_service.run(ctx.actor, mode=mode)
            return _format_service_result(result)
        if command == "/learn":
            result = await self.agent_service.learn(ctx.actor)
            return _format_service_result(result)
        if command == "/reflect":
            result = await self.agent_service.reflect(ctx.actor)
            return _format_service_result(result)
        if command == "/positions":
            result = await self.agent_service.positions(ctx.actor)
            return _format_service_result(result)
        if command == "/pending":
            result = await self.order_service.pending(ctx.actor)
            return _format_service_result(result)
        if command == "/approve":
            order_id = _required_arg(ctx.args, 0, "Usage: /approve <order_id>")
            result = await self.order_service.approve(ctx.actor, order_id=order_id)
            return _format_service_result(result)
        if command == "/reject":
            order_id = _required_arg(ctx.args, 0, "Usage: /reject <order_id>")
            result = await self.order_service.reject(ctx.actor, order_id=order_id)
            return _format_service_result(result)
        if command == "/kill":
            mode = _arg_or_default(ctx.args, 0, "soft")
            if mode not in {"soft", "cancel", "flatten"}:
                return "Usage: /kill [soft|cancel|flatten]"
            result = await self.kill_switch_service.kill(
                ctx.actor,
                mode=mode,
                reason="telegram command",
            )
            return _format_service_result(result)
        if command == "/resume":
            result = await self.kill_switch_service.resume(ctx.actor)
            return _format_service_result(result)
        if command == "/memory":
            query = _required_arg(ctx.args, 0, "Usage: /memory <query>")
            result = await self.agent_service.memory_search(ctx.actor, query=query)
            return _format_service_result(result)
        if command == "/skills":
            result = await self.agent_service.skills(ctx.actor)
            return _format_service_result(result)
        if command == "/heartbeat":
            result = await self.kill_switch_service.heartbeat(ctx.actor, source="telegram")
            return _format_service_result(result)
        return "Comando non supportato."

    async def _run_with_timeout(self, coroutine: Any) -> str:
        task = asyncio.create_task(coroutine)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self.config.command_timeout_seconds)
        except asyncio.TimeoutError:
            return TIMEOUT_MESSAGE

    async def _audit(self, chat_id: str, command: str, outcome: str, detail: str) -> None:
        await self.audit_service.log_command(
            chat_id=chat_id,
            command=command,
            outcome=outcome,
            detail=detail,
            ts_utc=datetime.now(UTC).isoformat(),
        )


def _parse_command(chat_id: str, actor: str, raw_text: str) -> CommandContext | None:
    if not raw_text.startswith("/"):
        return None
    parts = raw_text.split()
    command = parts[0].strip().lower()
    args = tuple(parts[1:])
    supported = {
        "/status",
        "/plan",
        "/run",
        "/learn",
        "/reflect",
        "/positions",
        "/pending",
        "/approve",
        "/reject",
        "/kill",
        "/resume",
        "/memory",
        "/skills",
        "/heartbeat",
    }
    if command not in supported:
        return None
    return CommandContext(
        chat_id=chat_id,
        actor=actor,
        raw_text=raw_text,
        command=command,
        args=args,
    )


def _arg_or_default(args: tuple[str, ...], index: int, default: str) -> str:
    try:
        value = args[index].strip()
    except IndexError:
        return default
    return value or default


def _required_arg(args: tuple[str, ...], index: int, usage: str) -> str:
    try:
        value = args[index].strip()
    except IndexError as exc:
        raise ValueError(usage) from exc
    if not value:
        raise ValueError(usage)
    return value


def _is_money_touching(ctx: CommandContext) -> bool:
    if ctx.command == "/run":
        mode = _arg_or_default(ctx.args, 0, "auto").lower()
        return mode == "live"
    if ctx.command == "/approve":
        return True
    if ctx.command == "/kill":
        return True
    if ctx.command == "/resume":
        return True
    return False


def _format_service_result(result: ServiceResult) -> str:
    sanitized = sanitize_output(
        {
            "ok": result.ok,
            "message": result.message,
            "data": result.data,
        }
    )
    message = str(sanitized.get("message", "")).strip()
    data = sanitized.get("data", {})
    if not isinstance(data, dict):
        data = {}
    if not data:
        return message or ("OK" if result.ok else "Operazione rifiutata.")
    lines = [message] if message else []
    for key, value in sorted(data.items()):
        lines.append(f"{key}: {value}")
    return "\n".join(lines)

