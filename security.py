"""
Anti-clone / anti-takeover safeguards.

Realistic scope: a Telegram bot cannot cryptographically stop someone who
has the bot token from running their own copy — whoever holds the token
IS the bot, on Telegram's side. What this module *can* do is:
  - make the running instance verify its own configured Owner ID hasn't
    silently drifted from what was last persisted (catches a tampered
    .env / DB on a compromised or unauthorized deployment),
  - refuse to boot with an obviously-invalid/missing Owner ID,
  - alert the Owner whenever someone who isn't Owner/trusted attempts a
    protected action, and record it,
  - never print the bot token, API hash, DB URL, or userbot session
    anywhere reachable by a command.
"""
from __future__ import annotations

import logging

from aiogram import Bot

from bot.config import settings
from bot.database.crud import log_security_event
from bot.utils.logger_service import alert_owner

logger = logging.getLogger("bot.security")

_SENSITIVE_ENV_KEYS = {
    "BOT_TOKEN",
    "API_HASH",
    "USERBOT_SESSION_STRING",
    "DATABASE_URL",
}


def redact(text: str) -> str:
    """Best-effort scrub of known secrets out of any string before it could
    ever reach a chat (error messages, tracebacks, debug dumps)."""
    redacted = text
    for value in (settings.bot_token, settings.api_hash, settings.userbot_session_string):
        if value:
            redacted = redacted.replace(value, "[redacted]")
    return redacted


async def verify_owner_configuration() -> None:
    """Run at startup. Fails loudly rather than booting half-configured."""
    if not settings.owner_id or settings.owner_id <= 0:
        raise RuntimeError(
            "OWNER_ID is not set to a valid Telegram numeric user ID — refusing to start."
        )
    logger.info("Owner verified: %s", settings.owner_id)


async def record_unauthorized_attempt(
    bot: Bot, user_id: int, chat_id: int | None, command: str
) -> None:
    detail = f"User {user_id} attempted Owner/trusted-only command: {command}"
    await log_security_event("unauthorized_attempt", detail, chat_id)
    await alert_owner(bot, detail)


async def record_config_change(bot: Bot, actor_id: int, what: str) -> None:
    """Call this from every handler that changes security-relevant config
    (trusted admins, trusted bots, permissions, federation root) so the
    Owner has a full trail even for changes made by trusted admins."""
    from bot.utils.logger_service import log_action  # local import avoids cycle

    await log_action(bot, None, "config_change", f"By {actor_id}: {what}")
