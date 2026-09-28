from __future__ import annotations

import asyncio
import json

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import crud
from bot.utils.filters import IsGroupAdminOrHigher

router = Router(name="cleanup")

CATEGORIES = (
    "welcome", "moderation", "music", "command_responses", "join_notifications", "temporary_info",
)

_DEFAULT_DELAYS = {  # seconds; 0 = never auto-delete
    "welcome": 0,
    "moderation": 0,
    "music": 0,
    "command_responses": 0,
    "join_notifications": 0,
    "temporary_info": 30,
}


async def get_cleanup_config(chat_id: int) -> dict:
    cfg = await crud.get_or_create_group_config(chat_id)
    if cfg.cleanup_config_json:
        try:
            stored = json.loads(cfg.cleanup_config_json)
            return {**_DEFAULT_DELAYS, **stored}
        except json.JSONDecodeError:
            pass
    return dict(_DEFAULT_DELAYS)


async def maybe_autodelete(bot: Bot, chat_id: int, message_id: int, category: str) -> None:
    """Call this after sending a bot message in one of CATEGORIES to honor
    the Owner's configured cleanup delay for that category."""
    config = await get_cleanup_config(chat_id)
    delay = config.get(category, 0)
    if delay and delay > 0:
        asyncio.create_task(_delete_after(bot, chat_id, message_id, delay))


async def _delete_after(bot: Bot, chat_id: int, message_id: int, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:  # noqa: BLE001
        pass


@router.message(Command("cleanup"), IsGroupAdminOrHigher())
async def cmd_cleanup(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()
    if not args:
        config = await get_cleanup_config(message.chat.id)
        lines = [f"• {cat}: {seconds}s" + (" (off)" if seconds == 0 else "") for cat, seconds in config.items()]
        await message.reply(
            "<b>Cleanup settings</b> (0 = never auto-delete)\n" + "\n".join(lines) +
            f"\n\nSet with: /cleanup <{'|'.join(CATEGORIES)}> <seconds>",
            parse_mode="HTML",
        )
        return

    if len(args) != 2 or args[0] not in CATEGORIES or not args[1].isdigit():
        await message.reply(f"Usage: /cleanup <{'|'.join(CATEGORIES)}> <seconds>")
        return

    category, seconds = args[0], int(args[1])
    config = await get_cleanup_config(message.chat.id)
    config[category] = seconds
    await crud.update_group_config(message.chat.id, cleanup_config_json=json.dumps(config))
    await message.reply(f"✅ {category} messages will {'never auto-delete' if seconds == 0 else f'auto-delete after {seconds}s'}.")
