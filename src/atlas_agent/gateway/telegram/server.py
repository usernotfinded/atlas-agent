from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from atlas_agent.gateway.telegram.bot import TelegramCommandBot
from atlas_agent.gateway.telegram.config import (
    TelegramWebhookSettings,
    load_telegram_settings,
)


class TelegramWebhookServer:
    def __init__(
        self,
        *,
        bot: TelegramCommandBot,
        settings: TelegramWebhookSettings | None = None,
    ) -> None:
        self.bot = bot
        self.settings = settings or load_telegram_settings()
        self.app = FastAPI(title="Atlas Telegram Webhook")
        self._wire_routes()

    def _wire_routes(self) -> None:
        @self.app.get(self.settings.healthz_path)
        async def healthz() -> dict[str, Any]:
            return {
                "ok": True,
                "service": "atlas-telegram-webhook",
                "ts_utc": datetime.now(UTC).isoformat(),
            }

        @self.app.post(self.settings.webhook_path)
        async def telegram_webhook(
            request: Request,
            x_telegram_bot_api_secret_token: str | None = Header(
                default=None,
                alias="X-Telegram-Bot-Api-Secret-Token",
            ),
        ) -> dict[str, Any]:
            _verify_secret_token(
                expected=self.settings.webhook_secret_token,
                provided=x_telegram_bot_api_secret_token,
            )
            payload = await request.json()
            extracted = _extract_message(payload)
            if extracted is None:
                return {"ok": True, "handled": False, "detail": "unsupported update"}
            response_text = await self.bot.handle_text(
                chat_id=extracted["chat_id"],
                text=extracted["text"],
                actor=extracted["actor"],
            )
            return {
                "ok": True,
                "handled": True,
                "chat_id": extracted["chat_id"],
                "response": response_text,
            }


def create_fastapi_app(
    *,
    bot: TelegramCommandBot,
    settings: TelegramWebhookSettings | None = None,
) -> FastAPI:
    return TelegramWebhookServer(bot=bot, settings=settings).app


def _verify_secret_token(*, expected: str, provided: str | None) -> None:
    if not expected:
        raise HTTPException(status_code=500, detail="webhook secret token is not configured")
    if not provided or provided != expected:
        raise HTTPException(status_code=403, detail="invalid Telegram secret token")


def _extract_message(payload: Any) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    message = payload.get("message") or payload.get("edited_message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    sender = message.get("from")
    text = message.get("text")
    if not isinstance(chat, dict) or not isinstance(text, str):
        return None
    chat_id = str(chat.get("id", "")).strip()
    user_id = ""
    if isinstance(sender, dict):
        user_id = str(sender.get("id", "")).strip()
    if not chat_id:
        return None
    actor = f"user:{user_id or chat_id}"
    return {
        "chat_id": chat_id,
        "actor": actor,
        "text": text,
    }

