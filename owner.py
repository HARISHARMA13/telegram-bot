from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import settings
from bot.database import crud
from bot.database.models import PermissionLevel
from bot.utils.filters import IsOwner, IsOwnerOrTrusted
from bot.utils.logger_service import log_action
from bot.utils.security import record_config_change, record_unauthorized_attempt

router = Router(name="owner")


def _parse_target_id(command: CommandObject, message: Message) -> int | None:
    if message.reply_to_message:
        return message.reply_to_message.from_user.id
    if command.args:
        first = command.args.split()[0]
        if first.isdigit():
            return int(first)
    return None


# ── /owner — top-level panel ────────────────────────────────────────────
@router.message(Command("owner"))
async def cmd_owner(message: Message, bot: Bot) -> None:
    if message.from_user.id != settings.owner_id:
        await record_unauthorized_attempt(bot, message.from_user.id, message.chat.id, "/owner")
        await message.reply("Only the bot Owner can use this command.")
        return

    text = (
        "<b>Owner Control Panel</b>\n\n"
        f"Owner ID: <code>{settings.owner_id}</code>\n\n"
        "Available panels:\n"
        "/settings – per-group configuration\n"
        "/security – security status &amp; alerts\n"
        "/trustedadmin – manage trusted admins\n"
        "/trustedbot – manage trusted bots\n"
        "/logs – configure the audit log destination\n"
        "/federation – federation management\n"
        "/permissions – per-command permission levels\n"
        "/cleanup – auto-delete configuration\n"
        "/status – bot &amp; database health"
    )
    await message.reply(text, parse_mode="HTML")


# ── /status ──────────────────────────────────────────────────────────────
@router.message(Command("status"), IsOwnerOrTrusted())
async def cmd_status(message: Message) -> None:
    from bot.database.engine import engine

    db_ok = True
    try:
        async with engine.connect():
            pass
    except Exception:  # noqa: BLE001
        db_ok = False

    trusted_admins = await crud.list_trusted_admins()
    trusted_bots = await crud.list_trusted_bots()

    await message.reply(
        "<b>Status</b>\n"
        f"Database: {'✅ connected' if db_ok else '❌ unreachable'}\n"
        f"Trusted admins: {len(trusted_admins)}\n"
        f"Trusted bots: {len(trusted_bots)}\n"
        f"Log channel configured: {'yes' if settings.log_chat_id else 'no'}",
        parse_mode="HTML",
    )


# ── /security ────────────────────────────────────────────────────────────
@router.message(Command("security"), IsOwner())
async def cmd_security(message: Message) -> None:
    await message.reply(
        "<b>Security</b>\n"
        "- Owner ID is fixed at startup from the environment and cannot be changed at runtime.\n"
        "- Owner-only commands are gated independently of Telegram group-admin status.\n"
        "- Unauthorized attempts on protected commands are logged and alert the Owner.\n"
        "- No command exposes the bot token, API hash, DB URL, or userbot session.",
        parse_mode="HTML",
    )


# ── /trustedadmin ────────────────────────────────────────────────────────
@router.message(Command("trustedadmin"), IsOwner())
async def cmd_trustedadmin(message: Message, command: CommandObject, bot: Bot) -> None:
    args = (command.args or "").split()
    sub = args[0].lower() if args else "list"

    if sub == "list":
        admins = await crud.list_trusted_admins()
        if not admins:
            await message.reply("No trusted admins configured.")
            return
        lines = [f"• <code>{a.user_id}</code>" + (f" — {a.note}" if a.note else "") for a in admins]
        await message.reply("<b>Trusted admins:</b>\n" + "\n".join(lines), parse_mode="HTML")
        return

    if sub in ("add", "remove") and len(args) < 1:
        await message.reply("Usage: /trustedadmin add|remove <user_id> (or reply to a user)")
        return

    target_id = _parse_target_id(command, message)
    if target_id is None and len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])

    if target_id is None:
        await message.reply("Couldn't determine a target user. Reply to them or pass their numeric ID.")
        return

    if sub == "add":
        await crud.add_trusted_admin(target_id, added_by=message.from_user.id)
        await record_config_change(bot, message.from_user.id, f"added trusted admin {target_id}")
        await message.reply(f"✅ <code>{target_id}</code> is now a trusted admin.", parse_mode="HTML")
    elif sub == "remove":
        removed = await crud.remove_trusted_admin(target_id)
        if removed:
            await record_config_change(bot, message.from_user.id, f"removed trusted admin {target_id}")
        await message.reply(
            f"{'✅ Removed' if removed else 'That user was not a trusted admin.'}", parse_mode="HTML"
        )
    else:
        await message.reply("Usage: /trustedadmin list|add|remove [user_id]")


# ── /trustedbot ──────────────────────────────────────────────────────────
@router.message(Command("trustedbot"), IsOwner())
async def cmd_trustedbot(message: Message, command: CommandObject, bot: Bot) -> None:
    args = (command.args or "").split()
    sub = args[0].lower() if args else "list"

    if sub == "list":
        bots = await crud.list_trusted_bots()
        if not bots:
            await message.reply("No trusted bots configured.")
            return
        lines = [f"• <code>{b.bot_id}</code>" + (f" (@{b.username})" if b.username else "") for b in bots]
        await message.reply("<b>Trusted bots:</b>\n" + "\n".join(lines), parse_mode="HTML")
        return

    if len(args) < 2 or not args[1].isdigit():
        await message.reply("Usage: /trustedbot add|remove <bot_id>")
        return

    bot_id = int(args[1])
    if sub == "add":
        await crud.add_trusted_bot(bot_id, added_by=message.from_user.id)
        await record_config_change(bot, message.from_user.id, f"added trusted bot {bot_id}")
        await message.reply(f"✅ Bot <code>{bot_id}</code> is now trusted.", parse_mode="HTML")
    elif sub == "remove":
        removed = await crud.remove_trusted_bot(bot_id)
        if removed:
            await record_config_change(bot, message.from_user.id, f"removed trusted bot {bot_id}")
        await message.reply("✅ Removed." if removed else "That bot wasn't trusted.")
    else:
        await message.reply("Usage: /trustedbot list|add|remove <bot_id>")


# ── /logs ────────────────────────────────────────────────────────────────
@router.message(Command("logs"), IsOwner())
async def cmd_logs(message: Message) -> None:
    configured = f"<code>{settings.log_chat_id}</code>" if settings.log_chat_id else "not set"
    await message.reply(
        "<b>Audit log destination</b>\n"
        f"Current LOG_CHAT_ID: {configured}\n"
        "To change it, update LOG_CHAT_ID in the environment and restart the bot "
        "(kept out of runtime commands intentionally so it can't be redirected on the fly).",
        parse_mode="HTML",
    )


# ── /permissions ─────────────────────────────────────────────────────────
_CONFIGURABLE_COMMANDS = {
    "ban", "unban", "kick", "mute", "unmute", "tban", "tmute", "warn", "unwarn",
    "purge", "del", "lock", "unlock", "filter", "unfilter", "blacklist", "whitelist",
    "note", "notes", "pin", "play", "skip", "queue",
}

_PROTECTED_COMMANDS = {
    "owner", "security", "trustedadmin", "trustedbot", "logs", "federation",
    "permissions", "cleanup", "status",
}


@router.message(Command("permissions"), IsOwner())
async def cmd_permissions(message: Message, command: CommandObject, bot: Bot) -> None:
    args = (command.args or "").split()
    if not args:
        await message.reply(
            "Usage: /permissions <command> <owner|trusted|admin|all>\n"
            f"Configurable commands: {', '.join(sorted(_CONFIGURABLE_COMMANDS))}\n\n"
            "Note: security/bot/federation/owner commands are always Owner-only "
            "and cannot be reconfigured here."
        )
        return

    cmd_name, *rest = args
    cmd_name = cmd_name.lstrip("/").lower()

    if cmd_name in _PROTECTED_COMMANDS:
        await message.reply(
            "That command controls security/config and can never be opened up beyond the Owner."
        )
        return

    if cmd_name not in _CONFIGURABLE_COMMANDS:
        await message.reply(f"Unknown or non-configurable command: {cmd_name}")
        return

    if not rest:
        level = await crud.get_command_permission(
            message.chat.id, cmd_name, PermissionLevel.GROUP_ADMIN
        )
        await message.reply(f"/{cmd_name} is currently: {level.value}")
        return

    mapping = {
        "owner": PermissionLevel.OWNER_ONLY,
        "trusted": PermissionLevel.OWNER_TRUSTED,
        "admin": PermissionLevel.GROUP_ADMIN,
        "all": PermissionLevel.ALL_MEMBERS,
    }
    level = mapping.get(rest[0].lower())
    if level is None:
        await message.reply("Level must be one of: owner, trusted, admin, all")
        return

    await crud.set_command_permission(message.chat.id, cmd_name, level)
    await record_config_change(bot, message.from_user.id, f"set /{cmd_name} permission to {level.value}")
    await message.reply(f"✅ /{cmd_name} is now: {level.value}")


# ── /settings ────────────────────────────────────────────────────────────
@router.message(Command("settings"), IsOwnerOrTrusted())
async def cmd_settings(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Use this inside the group you want to configure.")
        return
    cfg = await crud.get_or_create_group_config(message.chat.id, message.chat.title)
    await message.reply(
        "<b>Group settings</b>\n"
        f"Welcome enabled: {cfg.welcome_enabled}\n"
        f"Auto-approve join requests: {cfg.auto_approve_join_requests}\n"
        f"Lock media/links/stickers/gifs/forwards: "
        f"{cfg.lock_media}/{cfg.lock_links}/{cfg.lock_stickers}/{cfg.lock_gifs}/{cfg.lock_forwards}\n"
        f"Anti-flood: {cfg.antiflood_enabled} "
        f"({cfg.antiflood_max_messages} msgs / {cfg.antiflood_window_seconds}s → {cfg.antiflood_action})\n"
        f"Warn limit: {cfg.warn_limit} → {cfg.warn_action}\n"
        f"Music restricted to admins: {cfg.music_restricted_to_admins}\n\n"
        "Use the dedicated commands (/lockmedia, /antiflood, /warnlimit, etc.) to change these.",
        parse_mode="HTML",
    )
