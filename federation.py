from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import crud
from bot.utils.filters import IsOwner, IsOwnerOrTrusted
from bot.utils.logger_service import log_action
from bot.utils.parsing import resolve_target
from bot.utils.security import record_config_change

router = Router(name="federation")


async def _require_federation(message: Message) -> int | None:
    fed_id = await crud.get_chat_federation_id(message.chat.id)
    if fed_id is None:
        await message.reply("This group isn't linked to a federation. Use /fjoin <fed_id> first.")
    return fed_id


# Creating/administering a federation's root is Owner-only, by design —
# per-federation admins are then delegated to handle day-to-day bans.
@router.message(Command("fnew"), IsOwner())
async def cmd_fnew(message: Message, command: CommandObject, bot: Bot) -> None:
    if not command.args:
        await message.reply("Usage: /fnew <federation name>")
        return
    fed = await crud.create_federation(command.args.strip(), message.from_user.id)
    await crud.link_chat_to_federation(fed.id, message.chat.id)
    await record_config_change(bot, message.from_user.id, f"created federation '{fed.name}' (id={fed.id})")
    await message.reply(f"✅ Federation '{fed.name}' created with ID <code>{fed.id}</code>.", parse_mode="HTML")


@router.message(Command("fjoin"), IsOwnerOrTrusted())
async def cmd_fjoin(message: Message, command: CommandObject, bot: Bot) -> None:
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /fjoin <federation_id>")
        return
    await crud.link_chat_to_federation(int(command.args), message.chat.id)
    await record_config_change(bot, message.from_user.id, f"linked chat {message.chat.id} to federation {command.args}")
    await message.reply("✅ This group is now part of that federation.")


@router.message(Command("fadmin"), IsOwner())
async def cmd_fadmin(message: Message, command: CommandObject, bot: Bot) -> None:
    fed_id = await _require_federation(message)
    if fed_id is None:
        return
    target_id, _ = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Usage: /fadmin add|remove <user_id> (reply supported)")
        return
    args = (command.args or "").split()
    sub = args[0].lower() if args else "add"
    if sub == "remove":
        await crud.remove_federation_admin(fed_id, target_id)
        await message.reply(f"✅ Removed federation admin <code>{target_id}</code>.", parse_mode="HTML")
    else:
        await crud.add_federation_admin(fed_id, target_id)
        await message.reply(f"✅ Added federation admin <code>{target_id}</code>.", parse_mode="HTML")
    await record_config_change(bot, message.from_user.id, f"fed {fed_id} admin change: {sub} {target_id}")


@router.message(Command("fban"), IsOwnerOrTrusted())
async def cmd_fban(message: Message, command: CommandObject, bot: Bot) -> None:
    fed_id = await _require_federation(message)
    if fed_id is None:
        return
    target_id, reason = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Usage: /fban <user_id> [reason] (reply supported)")
        return
    await crud.fban_user(fed_id, target_id, message.from_user.id, reason)
    chats = await crud.get_federation_chats(fed_id)
    applied = 0
    for chat_id in chats:
        try:
            await bot.ban_chat_member(chat_id, target_id)
            applied += 1
        except Exception:  # noqa: BLE001 — bot may not be admin in every fed chat
            continue
    await log_action(
        bot, None, "federation",
        f"{message.from_user.id} fbanned {target_id} in fed {fed_id} ({applied}/{len(chats)} chats)",
    )
    await message.reply(f"🔨 Federation-banned <code>{target_id}</code> in {applied}/{len(chats)} chats.", parse_mode="HTML")


@router.message(Command("funban"), IsOwnerOrTrusted())
async def cmd_funban(message: Message, command: CommandObject, bot: Bot) -> None:
    fed_id = await _require_federation(message)
    if fed_id is None:
        return
    target_id, _ = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Usage: /funban <user_id>")
        return
    removed = await crud.fun_ban_user(fed_id, target_id)
    if removed:
        chats = await crud.get_federation_chats(fed_id)
        for chat_id in chats:
            try:
                await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
            except Exception:  # noqa: BLE001
                continue
        await log_action(bot, None, "federation", f"{message.from_user.id} un-fbanned {target_id} in fed {fed_id}")
    await message.reply("✅ Un-fbanned." if removed else "That user wasn't fbanned.")


@router.message(Command("fedinfo"))
async def cmd_fedinfo(message: Message) -> None:
    fed_id = await crud.get_chat_federation_id(message.chat.id)
    if fed_id is None:
        await message.reply("This group is not part of any federation.")
        return
    chats = await crud.get_federation_chats(fed_id)
    await message.reply(f"Federation ID: <code>{fed_id}</code>\nLinked chats: {len(chats)}", parse_mode="HTML")
