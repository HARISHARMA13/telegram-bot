"""
Permission filters. These are the ONLY gate that Owner-only / sensitive
commands should rely on — never trust Telegram's own "is chat admin"
status for Owner-level actions, since group-admin rights are independent
of bot Ownership per the security spec.
"""
from __future__ import annotations

from aiogram import types
from aiogram.filters import BaseFilter

from bot.config import settings
from bot.database.crud import get_command_permission, is_trusted_admin
from bot.database.models import PermissionLevel


def is_owner(user_id: int) -> bool:
    return user_id == settings.owner_id


async def is_owner_or_trusted(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    if user_id in settings.extra_trusted_admin_ids:
        return True
    return await is_trusted_admin(user_id)


async def is_chat_admin(message: types.Message) -> bool:
    if message.chat.type == "private":
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ("administrator", "creator")


class IsOwner(BaseFilter):
    """Owner-only. Used for security, federation-root, and core config commands."""

    async def __call__(self, message: types.Message) -> bool:
        return is_owner(message.from_user.id)


class IsOwnerOrTrusted(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return await is_owner_or_trusted(message.from_user.id)


class IsGroupAdminOrHigher(BaseFilter):
    """Owner, trusted admin, OR a real Telegram admin of this group."""

    async def __call__(self, message: types.Message) -> bool:
        if await is_owner_or_trusted(message.from_user.id):
            return True
        return await is_chat_admin(message)


class ConfigurablePermission(BaseFilter):
    """
    Checks a command against the Owner-configured permission level
    (owner_only / owner_trusted / group_admin / all_members), falling
    back to a sane default if never configured.

    NOTE: commands that touch security/bots/federation/owner settings
    must be registered with a hard-coded IsOwner / IsOwnerOrTrusted
    filter, never routed through this — the Owner should not be able
    to accidentally open those up via /permissions.
    """

    def __init__(self, command: str, default: PermissionLevel = PermissionLevel.GROUP_ADMIN):
        self.command = command
        self.default = default

    async def __call__(self, message: types.Message) -> bool:
        level = await get_command_permission(message.chat.id, self.command, self.default)
        if level == PermissionLevel.ALL_MEMBERS:
            return True
        if level == PermissionLevel.GROUP_ADMIN:
            return await IsGroupAdminOrHigher()(message)
        if level == PermissionLevel.OWNER_TRUSTED:
            return await is_owner_or_trusted(message.from_user.id)
        return is_owner(message.from_user.id)  # OWNER_ONLY
