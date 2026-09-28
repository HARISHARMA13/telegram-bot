from __future__ import annotations

import json

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import crud
from bot.utils.filters import IsGroupAdminOrHigher
from bot.utils.logger_service import log_action

router = Router(name="pinned")


def _keyboard_from_json(buttons_json: str | None) -> InlineKeyboardMarkup | None:
    if not buttons_json:
        return None
    try:
        rows = json.loads(buttons_json)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row] for row in rows
            ]
        )
    except Exception:  # noqa: BLE001
        return None


def _parse_buttons_arg(raw: str) -> str:
    rows = []
    for row_text in raw.split(";"):
        row = []
        for btn_text in row_text.split(","):
            if "|" not in btn_text:
                continue
            label, url = btn_text.split("|", 1)
            row.append({"text": label.strip(), "url": url.strip()})
        if row:
            rows.append(row)
    return json.dumps(rows)


@router.message(Command("setinfo"), IsGroupAdminOrHigher())
async def cmd_setinfo(message: Message, command: CommandObject) -> None:
    """
    /setinfo <name> | <text> || Label|https://url, Label2|https://url2 ; Label3|https://url3
    The button section (after `||`) is optional.
    """
    if not command.args or "|" not in command.args:
        await message.reply(
            "Usage: /setinfo <name> | <text> [|| buttons]\n"
            "Buttons: Label|https://url, Label2|https://url2 ; NewRowLabel|https://url3"
        )
        return

    name_part, remainder = command.args.split("|", 1)
    name = name_part.strip().lower()

    buttons_json = None
    if "||" in remainder:
        text_part, buttons_part = remainder.split("||", 1)
        buttons_json = _parse_buttons_arg(buttons_part.strip())
    else:
        text_part = remainder

    await crud.save_pinned_info(message.chat.id, name, text_part.strip(), message.from_user.id, buttons_json)
    await message.reply(f"✅ Info '{name}' saved. Use /pininfo {name} to post and pin it.")


@router.message(Command("pininfo"), IsGroupAdminOrHigher())
async def cmd_pininfo(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args:
        await message.reply("Usage: /pininfo <name>")
        return
    name = command.args.strip().lower()
    info = await crud.get_pinned_info(message.chat.id, name)
    if not info:
        await message.reply("No such info entry. Create one with /setinfo first.")
        return

    keyboard = _keyboard_from_json(info.buttons_json)
    sent = await bot.send_message(message.chat.id, info.content_text, reply_markup=keyboard)
    await crud.set_pinned_message_id(message.chat.id, name, sent.message_id)
    try:
        await bot.pin_chat_message(message.chat.id, sent.message_id)
    except TelegramBadRequest:
        await message.reply("Posted, but I don't have permission to pin messages here.")
        return
    await log_action(bot, message.chat.id, "config_change", f"{message.from_user.id} pinned info '{name}'")


@router.message(Command("unpininfo"), IsGroupAdminOrHigher())
async def cmd_unpininfo(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args:
        await message.reply("Usage: /unpininfo <name>")
        return
    info = await crud.get_pinned_info(message.chat.id, command.args.strip().lower())
    if not info or not info.message_id:
        await message.reply("That info isn't currently pinned.")
        return
    try:
        await bot.unpin_chat_message(message.chat.id, info.message_id)
    except TelegramBadRequest:
        pass
    await message.reply("✅ Unpinned.")


@router.message(Command("editinfo"), IsGroupAdminOrHigher())
async def cmd_editinfo(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args or "|" not in command.args:
        await message.reply("Usage: /editinfo <name> | <new text>")
        return
    name_part, new_text = command.args.split("|", 1)
    name = name_part.strip().lower()
    info = await crud.get_pinned_info(message.chat.id, name)
    if not info:
        await message.reply("No such info entry.")
        return
    updated = await crud.save_pinned_info(
        message.chat.id, name, new_text.strip(), message.from_user.id, info.buttons_json
    )
    if updated.message_id:
        try:
            await bot.edit_message_text(
                new_text.strip(), chat_id=message.chat.id, message_id=updated.message_id
            )
        except TelegramBadRequest:
            pass
    await message.reply("✅ Updated.")
