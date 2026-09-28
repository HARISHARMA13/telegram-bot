"""
Runs on every ordinary group message (never on commands from the modules
above) to enforce: media/link/sticker/gif/forward locks, word filters,
blacklist, anti-flood, and the bot-level slow-mode fallback.

Registered with the lowest router priority so moderation/owner commands
are always matched first.
"""
from __future__ import annotations

import re
import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message
from cachetools import TTLCache

from bot.database import crud
from bot.utils.logger_service import log_action

router = Router(name="guard")

# chat_id -> user_id -> list[timestamps]  (bounded, auto-expiring)
_flood_tracker: TTLCache = TTLCache(maxsize=50_000, ttl=120)
# (chat_id, user_id) -> last message time, for the bot-level slow-mode fallback
_slowmode_tracker: TTLCache = TTLCache(maxsize=50_000, ttl=3600)

_NO_PERMS = ChatPermissions(can_send_messages=False)

_LINK_RE = re.compile(r"(https?://|t\.me/|www\.)", re.IGNORECASE)


async def _is_privileged(bot: Bot, chat_id: int, user_id: int) -> bool:
    from bot.config import settings
    from bot.utils.filters import is_owner_or_trusted

    if await is_owner_or_trusted(user_id):
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except TelegramBadRequest:
        return False


@router.message(F.chat.type.in_({"group", "supergroup"}), ~F.text.startswith("/"))
async def guard_message(message: Message, bot: Bot) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    if await _is_privileged(bot, chat_id, user_id):
        return

    cfg = await crud.get_or_create_group_config(chat_id, message.chat.title)

    # ── Locks ────────────────────────────────────────────────────────
    violated_lock = None
    if cfg.lock_links and message.text and _LINK_RE.search(message.text):
        violated_lock = "links"
    elif cfg.lock_media and (message.photo or message.video or message.audio or message.document):
        violated_lock = "media"
    elif cfg.lock_stickers and message.sticker:
        violated_lock = "stickers"
    elif cfg.lock_gifs and message.animation:
        violated_lock = "gifs"
    elif cfg.lock_forwards and (message.forward_date or message.forward_origin):
        violated_lock = "forwards"

    if violated_lock:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await log_action(bot, chat_id, "guard", f"deleted {violated_lock} from {user_id} (locked)")
        return

    # ── Word filters / blacklist ────────────────────────────────────
    if message.text:
        lowered = message.text.lower()
        filters_ = await crud.list_word_filters(chat_id)
        for f in filters_:
            if f.trigger in lowered:
                await _apply_filter_action(bot, message, f.action, f.response_text)
                return

        blacklist = await crud.get_list(chat_id, "blacklist")
        for word in blacklist:
            if word.lower() in lowered:
                try:
                    await message.delete()
                except TelegramBadRequest:
                    pass
                await log_action(bot, chat_id, "guard", f"deleted blacklisted word from {user_id}")
                return

    # ── Bot-level slow mode fallback ────────────────────────────────
    if cfg.slowmode_seconds > 0:
        key = (chat_id, user_id)
        now = time.monotonic()
        last = _slowmode_tracker.get(key)
        if last is not None and now - last < cfg.slowmode_seconds:
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return
        _slowmode_tracker[key] = now

    # ── Anti-flood ───────────────────────────────────────────────────
    if cfg.antiflood_enabled:
        key = f"{chat_id}:{user_id}"
        timestamps = _flood_tracker.get(key, [])
        now = time.monotonic()
        timestamps = [t for t in timestamps if now - t < cfg.antiflood_window_seconds]
        timestamps.append(now)
        _flood_tracker[key] = timestamps

        if len(timestamps) > cfg.antiflood_max_messages:
            _flood_tracker[key] = []
            await _apply_flood_action(bot, message, cfg.antiflood_action)


async def _apply_filter_action(bot: Bot, message: Message, action: str, response: str | None) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    if response:
        await bot.send_message(chat_id, response)

    if action == "warn":
        count = await crud.add_warning(chat_id, user_id, bot.id, "triggered word filter")
        await log_action(bot, chat_id, "guard", f"warned {user_id} via filter ({count})")
    elif action == "mute":
        await bot.restrict_chat_member(chat_id, user_id, permissions=_NO_PERMS)
        await log_action(bot, chat_id, "guard", f"muted {user_id} via filter")
    elif action == "ban":
        await bot.ban_chat_member(chat_id, user_id)
        await log_action(bot, chat_id, "guard", f"banned {user_id} via filter")
    else:
        await log_action(bot, chat_id, "guard", f"deleted message from {user_id} via filter")


async def _apply_flood_action(bot: Bot, message: Message, action: str) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id
    if action == "ban":
        await bot.ban_chat_member(chat_id, user_id)
    elif action == "kick":
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
    else:
        await bot.restrict_chat_member(chat_id, user_id, permissions=_NO_PERMS)
    await log_action(bot, chat_id, "guard", f"anti-flood {action} applied to {user_id}")
