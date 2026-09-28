from __future__ import annotations

import asyncio
import json

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database import crud
from bot.utils.filters import ConfigurablePermission, IsGroupAdminOrHigher
from bot.utils.logger_service import log_action

router = Router(name="welcome")


def _build_keyboard(buttons_json: str | None) -> InlineKeyboardMarkup | None:
    if not buttons_json:
        return None
    try:
        rows = json.loads(buttons_json)
        keyboard = [
            [InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row] for row in rows
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _render_welcome(template: str, user_first_name: str, username: str | None, chat_title: str) -> str:
    return (
        template.replace("{first_name}", user_first_name)
        .replace("{username}", f"@{username}" if username else user_first_name)
        .replace("{chat}", chat_title)
    )


# ── Configure welcome ────────────────────────────────────────────────────
@router.message(Command("setwelcome"), IsGroupAdminOrHigher())
async def cmd_setwelcome(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.reply(
            "Usage: /setwelcome <text>\n"
            "Placeholders: {first_name}, {username}, {chat}\n"
            "Add buttons with /setwelcomebuttons afterwards."
        )
        return
    await crud.update_group_config(
        message.chat.id, welcome_enabled=True, welcome_text=command.args
    )
    await message.reply("✅ Welcome message set and enabled.")


@router.message(Command("setwelcomebuttons"), IsGroupAdminOrHigher())
async def cmd_setwelcomebuttons(message: Message, command: CommandObject) -> None:
    """Format: Label1|https://url1 ; Label2|https://url2 -- one row per ';' group, comma to add a column."""
    if not command.args:
        await message.reply(
            "Usage: /setwelcomebuttons Label|https://url, Label2|https://url2 ; Label3|https://url3\n"
            "Commas = same row, semicolons = new row."
        )
        return
    rows = []
    for row_text in command.args.split(";"):
        row = []
        for btn_text in row_text.split(","):
            if "|" not in btn_text:
                continue
            label, url = btn_text.split("|", 1)
            row.append({"text": label.strip(), "url": url.strip()})
        if row:
            rows.append(row)
    await crud.update_group_config(message.chat.id, welcome_buttons_json=json.dumps(rows))
    await message.reply("✅ Welcome buttons set.")


@router.message(Command("welcomeautodelete"), IsGroupAdminOrHigher())
async def cmd_welcome_autodelete(message: Message, command: CommandObject) -> None:
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /welcomeautodelete <seconds> (0 to disable)")
        return
    await crud.update_group_config(message.chat.id, welcome_autodelete_seconds=int(command.args))
    await message.reply(f"✅ Welcome messages will auto-delete after {command.args}s.")


@router.message(Command("togglewelcome"), IsGroupAdminOrHigher())
async def cmd_togglewelcome(message: Message, command: CommandObject) -> None:
    state = (command.args or "").strip().lower()
    if state not in ("on", "off"):
        await message.reply("Usage: /togglewelcome on|off")
        return
    await crud.update_group_config(message.chat.id, welcome_enabled=(state == "on"))
    await message.reply(f"✅ Welcome messages {'enabled' if state == 'on' else 'disabled'}.")


# ── Actually greet new members ───────────────────────────────────────────
# Called from bot.handlers.member_events (the single chat_member entry
# point — see the note in bot_protection.py for why this isn't its own
# @router.chat_member() handler).
async def handle_member_joined(event: ChatMemberUpdated, bot: Bot) -> None:
    old, new = event.old_chat_member.status, event.new_chat_member.status
    if old in ("left", "kicked") and new == "member":
        cfg = await crud.get_or_create_group_config(event.chat.id, event.chat.title)
        if not cfg.welcome_enabled or not cfg.welcome_text:
            return
        user = event.new_chat_member.user
        text = _render_welcome(cfg.welcome_text, user.first_name, user.username, event.chat.title or "")
        keyboard = _build_keyboard(cfg.welcome_buttons_json)
        sent = await bot.send_message(event.chat.id, text, reply_markup=keyboard)
        if cfg.welcome_autodelete_seconds > 0:
            asyncio.create_task(_delete_later(bot, event.chat.id, sent.message_id, cfg.welcome_autodelete_seconds))


async def _delete_later(bot: Bot, chat_id: int, message_id: int, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:  # noqa: BLE001
        pass


# ── Join requests ────────────────────────────────────────────────────────
@router.chat_join_request()
async def on_join_request(event: ChatJoinRequest, bot: Bot) -> None:
    cfg = await crud.get_or_create_group_config(event.chat.id, event.chat.title)

    if cfg.log_join_requests:
        await log_action(
            bot, event.chat.id, "join_request",
            f"{event.from_user.id} (@{event.from_user.username}) requested to join",
        )

    # Per the spec: never auto-approve unless the Owner explicitly enabled it.
    if cfg.auto_approve_join_requests:
        await bot.approve_chat_join_request(event.chat.id, event.from_user.id)
        await log_action(bot, event.chat.id, "join_request", f"auto-approved {event.from_user.id}")


@router.message(Command("approve"), ConfigurablePermission("filter"))
async def cmd_approve(message: Message, command: CommandObject, bot: Bot) -> None:
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /approve <user_id>")
        return
    await bot.approve_chat_join_request(message.chat.id, int(command.args))
    await log_action(bot, message.chat.id, "join_request", f"{message.from_user.id} approved {command.args}")
    await message.reply("✅ Approved.")


@router.message(Command("reject"), ConfigurablePermission("filter"))
async def cmd_reject(message: Message, command: CommandObject, bot: Bot) -> None:
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /reject <user_id>")
        return
    await bot.decline_chat_join_request(message.chat.id, int(command.args))
    await log_action(bot, message.chat.id, "join_request", f"{message.from_user.id} rejected {command.args}")
    await message.reply("✅ Rejected.")


@router.message(Command("autoapprove"), IsGroupAdminOrHigher())
async def cmd_autoapprove(message: Message, command: CommandObject) -> None:
    state = (command.args or "").strip().lower()
    if state not in ("on", "off"):
        await message.reply("Usage: /autoapprove on|off")
        return
    await crud.update_group_config(message.chat.id, auto_approve_join_requests=(state == "on"))
    await message.reply(f"✅ Auto-approve join requests: {state}.")
