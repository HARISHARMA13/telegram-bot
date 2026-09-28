from __future__ import annotations

import json

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import crud
from bot.utils.filters import IsGroupAdminOrHigher
from bot.utils.logger_service import log_action

router = Router(name="notes")

_FILE_TYPE_MAP = {
    "photo": lambda m: m.photo[-1].file_id if m.photo else None,
    "video": lambda m: m.video.file_id if m.video else None,
    "document": lambda m: m.document.file_id if m.document else None,
    "animation": lambda m: m.animation.file_id if m.animation else None,
    "voice": lambda m: m.voice.file_id if m.voice else None,
    "audio": lambda m: m.audio.file_id if m.audio else None,
    "sticker": lambda m: m.sticker.file_id if m.sticker else None,
}


def _detect_file(message: Message) -> tuple[str | None, str | None]:
    for file_type, getter in _FILE_TYPE_MAP.items():
        file_id = getter(message)
        if file_id:
            return file_type, file_id
    return None, None


def _keyboard_from_json(buttons_json: str | None) -> InlineKeyboardMarkup | None:
    if not buttons_json:
        return None
    try:
        rows = json.loads(buttons_json)
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(**b) for b in row] for row in rows]
        )
    except Exception:  # noqa: BLE001
        return None


@router.message(Command("save"), IsGroupAdminOrHigher())
async def cmd_save(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args:
        await message.reply("Usage: /save <name> <content> (or reply to media with /save <name>)")
        return

    name, *rest = command.args.split(maxsplit=1)
    text_content = rest[0] if rest else None
    file_type, file_id = (None, None)

    source = message.reply_to_message or message
    if source is not message or message.reply_to_message:
        file_type, file_id = _detect_file(message.reply_to_message or message)
        if message.reply_to_message and message.reply_to_message.text and not text_content:
            text_content = message.reply_to_message.text

    await crud.save_note(
        chat_id=message.chat.id,
        name=name.lower(),
        created_by=message.from_user.id,
        content_text=text_content,
        file_id=file_id,
        file_type=file_type,
    )
    await log_action(bot, message.chat.id, "notes", f"{message.from_user.id} saved note '{name}'")
    await message.reply(f"✅ Saved note: <code>{name}</code>", parse_mode="HTML")


async def _send_note(message: Message, name: str) -> None:
    note = await crud.get_note(message.chat.id, name)
    if not note:
        await message.reply("No such note.")
        return
    keyboard = _keyboard_from_json(note.buttons_json)
    if note.file_id and note.file_type == "photo":
        await message.reply_photo(note.file_id, caption=note.content_text, reply_markup=keyboard)
    elif note.file_id and note.file_type == "video":
        await message.reply_video(note.file_id, caption=note.content_text, reply_markup=keyboard)
    elif note.file_id and note.file_type == "document":
        await message.reply_document(note.file_id, caption=note.content_text, reply_markup=keyboard)
    elif note.file_id and note.file_type == "animation":
        await message.reply_animation(note.file_id, caption=note.content_text, reply_markup=keyboard)
    elif note.file_id and note.file_type == "sticker":
        await message.reply_sticker(note.file_id)
    else:
        await message.reply(note.content_text or "(empty note)", reply_markup=keyboard)


@router.message(Command("get"))
async def cmd_get(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.reply("Usage: /get <name>")
        return
    await _send_note(message, command.args.strip().lower())


# Also support #notename shorthand, a common convention in moderation bots
@router.message(lambda m: m.text and m.text.startswith("#") and len(m.text) > 1)
async def hashtag_get(message: Message) -> None:
    name = message.text[1:].split()[0].lower()
    if await crud.get_note(message.chat.id, name):
        await _send_note(message, name)


@router.message(Command("notes"))
async def cmd_notes(message: Message) -> None:
    names = await crud.list_notes(message.chat.id)
    if not names:
        await message.reply("No notes saved in this chat yet.")
        return
    await message.reply("<b>Notes:</b>\n" + "\n".join(f"• {n}" for n in names), parse_mode="HTML")


@router.message(Command("clear"), IsGroupAdminOrHigher())
async def cmd_clear_note(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args:
        await message.reply("Usage: /clear <name>")
        return
    name = command.args.strip().lower()
    removed = await crud.delete_note(message.chat.id, name)
    if removed:
        await log_action(bot, message.chat.id, "notes", f"{message.from_user.id} deleted note '{name}'")
    await message.reply("✅ Deleted." if removed else "No such note.")
