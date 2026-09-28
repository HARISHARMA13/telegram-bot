"""
A bot account cannot join or stream into a Telegram voice chat by itself —
the Bot API has no such capability. This "assistant" userbot (a real
Telegram account, logged in via Pyrogram/MTProto) joins the voice chat on
the group's behalf; PyTgCalls drives the actual audio streaming. The
regular aiogram bot stays the only thing users talk to — /play, /skip,
etc. — and just tells this userbot what to do.

Keep the session string as secret as the bot token. Never expose it, log
it, or print it in any command output.
"""
from __future__ import annotations

import logging

from pyrogram import Client
from pytgcalls import PyTgCalls

from bot.config import settings

logger = logging.getLogger("bot.music.userbot")

userbot = Client(
    name="assistant",
    api_id=settings.api_id,
    api_hash=settings.api_hash,
    session_string=settings.userbot_session_string or None,
    in_memory=bool(settings.userbot_session_string),
)

call_py = PyTgCalls(userbot)


async def start_userbot() -> None:
    await userbot.start()
    await call_py.start()
    me = await userbot.get_me()
    logger.info("Userbot started as %s (id=%s)", me.first_name, me.id)
    if not settings.userbot_session_string:
        logger.warning(
            "No USERBOT_SESSION_STRING configured — you logged in interactively this run. "
            "Run `python -m bot.music.generate_session` once to produce a session string "
            "and save it into .env so future restarts don't need a fresh login."
        )


async def stop_userbot() -> None:
    try:
        await call_py.stop()
    except Exception:  # noqa: BLE001
        pass
    await userbot.stop()
