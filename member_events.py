"""
aiogram stops propagating an update after the first router handler that
matches it. Both the welcome system and unauthorized-bot detection react
to the same `chat_member` update type, so they're combined into this one
handler rather than fighting over which router gets registered first.
"""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated

from bot.handlers.bot_protection import handle_bot_join
from bot.handlers.welcome import handle_member_joined

router = Router(name="member_events")


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated, bot: Bot) -> None:
    new_user = event.new_chat_member.user
    if new_user.is_bot:
        await handle_bot_join(event, bot)
    else:
        await handle_member_joined(event, bot)
