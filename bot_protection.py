from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated

from bot.database import crud
from bot.utils.logger_service import alert_owner, log_action

# NOTE: this is a plain function, not its own router handler — it's called
# from bot.handlers.member_events, which is the single chat_member entry
# point for the whole bot. aiogram stops event propagation after the
# first router handler that matches a chat_member update, so welcome
# messages and unauthorized-bot detection must live in one place rather
# than two separate @router.chat_member() handlers.


async def handle_bot_join(event: ChatMemberUpdated, bot: Bot) -> None:
    new_member = event.new_chat_member.user
    if not new_member.is_bot:
        return
    if new_member.id == bot.id:
        return  # this is our own bot being added/promoted — nothing to police

    old_status, new_status = event.old_chat_member.status, event.new_chat_member.status
    if not (old_status in ("left", "kicked") and new_status == "member"):
        return

    if await crud.is_trusted_bot(new_member.id):
        return  # explicitly approved — do not interfere

    detail = f"Unrecognized bot @{new_member.username or new_member.id} added by {event.from_user.id}"
    await log_action(bot, event.chat.id, "security", detail)
    await alert_owner(bot, f"{detail} in chat {event.chat.id} ({event.chat.title}).")

    # Owner's security policy decides the default handling; conservative
    # default here is "remove and alert" rather than silently allowing it,
    # since an unapproved bot could be a takeover attempt.
    try:
        await bot.ban_chat_member(event.chat.id, new_member.id)
        await bot.unban_chat_member(event.chat.id, new_member.id)  # kick, don't permanently ban
        await log_action(bot, event.chat.id, "security", f"Removed unrecognized bot {new_member.id}")
    except TelegramBadRequest:
        await log_action(
            bot, event.chat.id, "security",
            f"Could not remove unrecognized bot {new_member.id} (insufficient permissions)",
        )
