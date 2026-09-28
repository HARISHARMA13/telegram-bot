from __future__ import annotations

import logging

from aiogram import Bot

from bot.config import settings
from bot.database.crud import log_security_event

logger = logging.getLogger("bot.audit")


async def log_action(bot: Bot, chat_id: int | None, category: str, text: str) -> None:
    """
    Writes an audit-log line for moderation/security/config/music events.
    Always persisted to DB; additionally forwarded to LOG_CHAT_ID if set.
    Never include tokens, credentials, or stack traces in `text`.
    """
    logger.info("[%s] chat=%s %s", category, chat_id, text)
    await log_security_event(category, text, chat_id)

    if settings.log_chat_id:
        try:
            await bot.send_message(
                settings.log_chat_id,
                f"<b>[{category}]</b>\nChat: <code>{chat_id}</code>\n{text}",
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001 — logging must never crash the bot
            logger.exception("Failed to deliver log message to LOG_CHAT_ID")


async def alert_owner(bot: Bot, text: str) -> None:
    """Direct-messages the Owner for high-priority security events."""
    try:
        await bot.send_message(settings.owner_id, f"⚠️ <b>Security alert</b>\n{text}", parse_mode="HTML")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to alert Owner directly")
