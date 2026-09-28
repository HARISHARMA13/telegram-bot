from __future__ import annotations

import datetime as dt

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, Message

from bot.database import crud
from bot.database.models import PermissionLevel
from bot.utils.filters import ConfigurablePermission
from bot.utils.logger_service import log_action
from bot.utils.parsing import parse_duration, resolve_target

router = Router(name="moderation")

_NO_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

_FULL_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


async def _guard_bot_can_moderate(message: Message, target_id: int) -> bool:
    """Never let the bot try to act on the Owner, itself, or someone who
    outranks it in Telegram's own admin hierarchy — that would just fail
    or, worse, look like the bot is bypassing real Telegram permissions."""
    from bot.config import settings

    if target_id == settings.owner_id:
        await message.reply("I won't act on the bot Owner.")
        return False
    me = await message.bot.get_me()
    if target_id == me.id:
        await message.reply("I won't act on myself.")
        return False
    try:
        member = await message.bot.get_chat_member(message.chat.id, target_id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.reply("I can't moderate another admin of this group.")
            return False
    except TelegramBadRequest:
        pass
    return True


# ── Ban / Unban / Kick ───────────────────────────────────────────────────
@router.message(Command("ban"), ConfigurablePermission("ban"))
async def cmd_ban(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, reason = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Reply to a user or pass their ID/@username: /ban <target> [reason]")
        return
    if not await _guard_bot_can_moderate(message, target_id):
        return
    await bot.ban_chat_member(message.chat.id, target_id)
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} banned {target_id} ({reason or 'no reason'})")
    await message.reply(f"🔨 Banned <code>{target_id}</code>.", parse_mode="HTML")


@router.message(Command("unban"), ConfigurablePermission("unban"))
async def cmd_unban(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, _ = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Usage: /unban <user_id/@username>")
        return
    await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} unbanned {target_id}")
    await message.reply(f"✅ Unbanned <code>{target_id}</code>.", parse_mode="HTML")


@router.message(Command("kick"), ConfigurablePermission("kick"))
async def cmd_kick(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, reason = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Reply to a user or pass their ID/@username: /kick <target> [reason]")
        return
    if not await _guard_bot_can_moderate(message, target_id):
        return
    await bot.ban_chat_member(message.chat.id, target_id)
    await bot.unban_chat_member(message.chat.id, target_id)  # ban+unban == kick
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} kicked {target_id} ({reason or 'no reason'})")
    await message.reply(f"👢 Kicked <code>{target_id}</code>.", parse_mode="HTML")


# ── Mute / Unmute / Temp mute / Temp ban ─────────────────────────────────
@router.message(Command("mute"), ConfigurablePermission("mute"))
async def cmd_mute(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, reason = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Reply to a user or pass their ID/@username: /mute <target> [reason]")
        return
    if not await _guard_bot_can_moderate(message, target_id):
        return
    await bot.restrict_chat_member(message.chat.id, target_id, permissions=_NO_PERMS)
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} muted {target_id} ({reason or 'no reason'})")
    await message.reply(f"🔇 Muted <code>{target_id}</code>.", parse_mode="HTML")


@router.message(Command("unmute"), ConfigurablePermission("unmute"))
async def cmd_unmute(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, _ = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Usage: /unmute <user_id/@username>")
        return
    await bot.restrict_chat_member(message.chat.id, target_id, permissions=_FULL_PERMS)
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} unmuted {target_id}")
    await message.reply(f"🔊 Unmuted <code>{target_id}</code>.", parse_mode="HTML")


@router.message(Command("tmute"), ConfigurablePermission("tmute"))
async def cmd_tmute(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, rest = await resolve_target(message, command)
    if target_id is None or not rest:
        await message.reply("Usage: /tmute <target> <duration e.g. 10m/2h/1d> [reason]")
        return
    duration_token, *reason_parts = rest.split(maxsplit=1)
    duration = parse_duration(duration_token)
    if duration is None:
        await message.reply("Invalid duration. Examples: 10m, 2h, 1d, 1w")
        return
    if not await _guard_bot_can_moderate(message, target_id):
        return
    until = dt.datetime.now(dt.timezone.utc) + duration
    await bot.restrict_chat_member(message.chat.id, target_id, permissions=_NO_PERMS, until_date=until)
    reason = reason_parts[0] if reason_parts else "no reason"
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} tmuted {target_id} for {duration_token} ({reason})")
    await message.reply(f"🔇 Muted <code>{target_id}</code> for {duration_token}.", parse_mode="HTML")


@router.message(Command("tban"), ConfigurablePermission("tban"))
async def cmd_tban(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, rest = await resolve_target(message, command)
    if target_id is None or not rest:
        await message.reply("Usage: /tban <target> <duration e.g. 10m/2h/1d> [reason]")
        return
    duration_token, *reason_parts = rest.split(maxsplit=1)
    duration = parse_duration(duration_token)
    if duration is None:
        await message.reply("Invalid duration. Examples: 10m, 2h, 1d, 1w")
        return
    if not await _guard_bot_can_moderate(message, target_id):
        return
    until = dt.datetime.now(dt.timezone.utc) + duration
    await bot.ban_chat_member(message.chat.id, target_id, until_date=until)
    reason = reason_parts[0] if reason_parts else "no reason"
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} tbanned {target_id} for {duration_token} ({reason})")
    await message.reply(f"🔨 Banned <code>{target_id}</code> for {duration_token}.", parse_mode="HTML")


# ── Warnings ─────────────────────────────────────────────────────────────
@router.message(Command("warn"), ConfigurablePermission("warn"))
async def cmd_warn(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, reason = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Reply to a user or pass their ID/@username: /warn <target> [reason]")
        return
    if not await _guard_bot_can_moderate(message, target_id):
        return

    count = await crud.add_warning(message.chat.id, target_id, message.from_user.id, reason)
    cfg = await crud.get_or_create_group_config(message.chat.id, message.chat.title)
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} warned {target_id} ({count}/{cfg.warn_limit})")

    if count >= cfg.warn_limit:
        await crud.clear_warnings(message.chat.id, target_id)
        if cfg.warn_action == "ban":
            await bot.ban_chat_member(message.chat.id, target_id)
            outcome = "banned"
        elif cfg.warn_action == "kick":
            await bot.ban_chat_member(message.chat.id, target_id)
            await bot.unban_chat_member(message.chat.id, target_id)
            outcome = "kicked"
        else:
            await bot.restrict_chat_member(message.chat.id, target_id, permissions=_NO_PERMS)
            outcome = "muted"
        await message.reply(
            f"⚠️ <code>{target_id}</code> reached {cfg.warn_limit} warnings and was {outcome}.",
            parse_mode="HTML",
        )
    else:
        await message.reply(
            f"⚠️ Warned <code>{target_id}</code> ({count}/{cfg.warn_limit}).", parse_mode="HTML"
        )


@router.message(Command("unwarn"), ConfigurablePermission("unwarn"))
async def cmd_unwarn(message: Message, command: CommandObject, bot: Bot) -> None:
    target_id, _ = await resolve_target(message, command)
    if target_id is None:
        await message.reply("Usage: /unwarn <user_id/@username>")
        return
    cleared = await crud.clear_warnings(message.chat.id, target_id)
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} cleared {cleared} warning(s) for {target_id}")
    await message.reply(f"✅ Cleared warnings for <code>{target_id}</code>.", parse_mode="HTML")


@router.message(Command("warnlimit"), ConfigurablePermission("warn", default=PermissionLevel.GROUP_ADMIN))
async def cmd_warnlimit(message: Message, command: CommandObject) -> None:
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /warnlimit <number>")
        return
    await crud.update_group_config(message.chat.id, warn_limit=int(command.args))
    await message.reply(f"✅ Warn limit set to {command.args}.")


# ── Delete / Purge ───────────────────────────────────────────────────────
@router.message(Command("del"), ConfigurablePermission("del"))
async def cmd_del(message: Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.reply("Reply to the message you want deleted.")
        return
    await bot.delete_message(message.chat.id, message.reply_to_message.message_id)
    await bot.delete_message(message.chat.id, message.message_id)


@router.message(Command("purge"), ConfigurablePermission("purge"))
async def cmd_purge(message: Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.reply("Reply to the message to purge from, up to here.")
        return
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    deleted = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            await bot.delete_message(message.chat.id, msg_id)
            deleted += 1
        except TelegramBadRequest:
            continue
    await log_action(bot, message.chat.id, "moderation", f"{message.from_user.id} purged {deleted} messages")


# ── Locks ────────────────────────────────────────────────────────────────
_LOCK_FIELDS = {
    "media": "lock_media",
    "links": "lock_links",
    "stickers": "lock_stickers",
    "gifs": "lock_gifs",
    "forwards": "lock_forwards",
}


@router.message(Command("lock"), ConfigurablePermission("lock"))
async def cmd_lock(message: Message, command: CommandObject) -> None:
    target = (command.args or "").strip().lower()
    field = _LOCK_FIELDS.get(target)
    if not field:
        await message.reply(f"Usage: /lock <{'|'.join(_LOCK_FIELDS)}>")
        return
    await crud.update_group_config(message.chat.id, **{field: True})
    await message.reply(f"🔒 Locked {target}.")


@router.message(Command("unlock"), ConfigurablePermission("unlock"))
async def cmd_unlock(message: Message, command: CommandObject) -> None:
    target = (command.args or "").strip().lower()
    field = _LOCK_FIELDS.get(target)
    if not field:
        await message.reply(f"Usage: /unlock <{'|'.join(_LOCK_FIELDS)}>")
        return
    await crud.update_group_config(message.chat.id, **{field: False})
    await message.reply(f"🔓 Unlocked {target}.")


# ── Filters / blacklist / whitelist ──────────────────────────────────────
@router.message(Command("filter"), ConfigurablePermission("filter"))
async def cmd_filter(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.reply("Usage: /filter <trigger> [action=delete|warn|mute|ban] <response>")
        return
    parts = command.args.split(maxsplit=2)
    trigger = parts[0]
    action = "delete"
    response = None
    if len(parts) > 1 and parts[1] in ("delete", "warn", "mute", "ban"):
        action = parts[1]
        response = parts[2] if len(parts) > 2 else None
    elif len(parts) > 1:
        response = " ".join(parts[1:])
    await crud.add_word_filter(message.chat.id, trigger, action, response)
    await message.reply(f"✅ Filter added for '{trigger}' → {action}.")


@router.message(Command("unfilter"), ConfigurablePermission("unfilter"))
async def cmd_unfilter(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.reply("Usage: /unfilter <trigger>")
        return
    removed = await crud.remove_word_filter(message.chat.id, command.args.strip())
    await message.reply("✅ Removed." if removed else "No such filter.")


@router.message(Command("blacklist"), ConfigurablePermission("blacklist"))
async def cmd_blacklist(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split(maxsplit=1)
    if not args:
        entries = await crud.get_list(message.chat.id, "blacklist")
        await message.reply("Blacklist:\n" + "\n".join(entries) if entries else "Blacklist is empty.")
        return
    sub, *rest = args
    if sub == "add" and rest:
        await crud.add_list_entry(message.chat.id, "blacklist", rest[0], message.from_user.id)
        await message.reply("✅ Added to blacklist.")
    elif sub == "remove" and rest:
        removed = await crud.remove_list_entry(message.chat.id, "blacklist", rest[0])
        await message.reply("✅ Removed." if removed else "Not found.")
    else:
        await message.reply("Usage: /blacklist [add|remove] <word>")


@router.message(Command("whitelist"), ConfigurablePermission("whitelist"))
async def cmd_whitelist(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split(maxsplit=1)
    if not args:
        entries = await crud.get_list(message.chat.id, "whitelist")
        await message.reply("Whitelist:\n" + "\n".join(entries) if entries else "Whitelist is empty.")
        return
    sub, *rest = args
    if sub == "add" and rest:
        await crud.add_list_entry(message.chat.id, "whitelist", rest[0], message.from_user.id)
        await message.reply("✅ Added to whitelist.")
    elif sub == "remove" and rest:
        removed = await crud.remove_list_entry(message.chat.id, "whitelist", rest[0])
        await message.reply("✅ Removed." if removed else "Not found.")
    else:
        await message.reply("Usage: /whitelist [add|remove] <word>")


# ── Anti-flood toggle & slow mode ────────────────────────────────────────
@router.message(Command("antiflood"), ConfigurablePermission("lock"))
async def cmd_antiflood(message: Message, command: CommandObject) -> None:
    args = (command.args or "").strip().lower()
    if args == "on":
        await crud.update_group_config(message.chat.id, antiflood_enabled=True)
        await message.reply("✅ Anti-flood enabled.")
    elif args == "off":
        await crud.update_group_config(message.chat.id, antiflood_enabled=False)
        await message.reply("✅ Anti-flood disabled.")
    else:
        await message.reply("Usage: /antiflood on|off")


@router.message(Command("slowmode"), ConfigurablePermission("lock"))
async def cmd_slowmode(message: Message, command: CommandObject, bot: Bot) -> None:
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /slowmode <seconds> (0 to disable)")
        return
    seconds = int(command.args)
    try:
        await bot.set_chat_permissions(message.chat.id, permissions=_FULL_PERMS)  # no-op safeguard
    except TelegramBadRequest:
        pass
    # Telegram's native slow-mode is only settable via chat administrators
    # in the client UI / MTProto messages.setSlowMode-equivalent, which the
    # Bot API does not currently expose. We store the intent and enforce a
    # best-effort per-user cooldown at the message-handling layer instead.
    await crud.update_group_config(message.chat.id, slowmode_seconds=seconds)
    await message.reply(
        f"✅ Slow mode intent set to {seconds}s. Enforced by the bot's own message filter "
        f"since the Bot API can't set Telegram's native slow mode."
    )
