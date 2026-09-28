"""
Thin data-access functions. Handlers should go through these rather than
building queries inline, so persistence stays consistent and swappable.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select

from bot.database.engine import get_session
from bot.database.models import (
    CommandPermission,
    Federation,
    FederationAdmin,
    FederationBan,
    FederationChat,
    GroupConfig,
    ListEntry,
    MusicSession,
    Note,
    PermissionLevel,
    PinnedInfo,
    SecurityEvent,
    TrustedAdmin,
    TrustedBot,
    Warning,
    WordFilter,
)


# ── Group config ─────────────────────────────────────────────────────────
async def get_or_create_group_config(chat_id: int, title: str | None = None) -> GroupConfig:
    async with get_session() as session:
        cfg = await session.get(GroupConfig, chat_id)
        if cfg is None:
            cfg = GroupConfig(chat_id=chat_id, title=title)
            session.add(cfg)
            await session.flush()
        elif title and cfg.title != title:
            cfg.title = title
        await session.refresh(cfg)
        return cfg


async def update_group_config(chat_id: int, **fields) -> GroupConfig:
    async with get_session() as session:
        cfg = await session.get(GroupConfig, chat_id)
        if cfg is None:
            cfg = GroupConfig(chat_id=chat_id)
            session.add(cfg)
        for key, value in fields.items():
            setattr(cfg, key, value)
        await session.flush()
        await session.refresh(cfg)
        return cfg


# ── Owner / trusted admins & bots ───────────────────────────────────────
async def add_trusted_admin(user_id: int, added_by: int, note: str | None = None) -> None:
    async with get_session() as session:
        if await session.get(TrustedAdmin, user_id) is None:
            session.add(TrustedAdmin(user_id=user_id, added_by=added_by, note=note))


async def remove_trusted_admin(user_id: int) -> bool:
    async with get_session() as session:
        row = await session.get(TrustedAdmin, user_id)
        if row is None:
            return False
        await session.delete(row)
        return True


async def list_trusted_admins() -> list[TrustedAdmin]:
    async with get_session() as session:
        result = await session.execute(select(TrustedAdmin))
        return list(result.scalars().all())


async def is_trusted_admin(user_id: int) -> bool:
    async with get_session() as session:
        return (await session.get(TrustedAdmin, user_id)) is not None


async def add_trusted_bot(bot_id: int, added_by: int, username: str | None = None) -> None:
    async with get_session() as session:
        if await session.get(TrustedBot, bot_id) is None:
            session.add(TrustedBot(bot_id=bot_id, added_by=added_by, username=username))


async def remove_trusted_bot(bot_id: int) -> bool:
    async with get_session() as session:
        row = await session.get(TrustedBot, bot_id)
        if row is None:
            return False
        await session.delete(row)
        return True


async def is_trusted_bot(bot_id: int) -> bool:
    async with get_session() as session:
        return (await session.get(TrustedBot, bot_id)) is not None


async def list_trusted_bots() -> list[TrustedBot]:
    async with get_session() as session:
        result = await session.execute(select(TrustedBot))
        return list(result.scalars().all())


# ── Command permissions ─────────────────────────────────────────────────
async def set_command_permission(chat_id: int, command: str, level: PermissionLevel) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(CommandPermission).where(
                CommandPermission.chat_id == chat_id, CommandPermission.command == command
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.level = level
        else:
            session.add(CommandPermission(chat_id=chat_id, command=command, level=level))


async def get_command_permission(
    chat_id: int, command: str, default: PermissionLevel
) -> PermissionLevel:
    async with get_session() as session:
        # Chat-specific override first, then global (chat_id=0) default.
        result = await session.execute(
            select(CommandPermission).where(
                CommandPermission.command == command,
                CommandPermission.chat_id.in_([chat_id, 0]),
            )
        )
        rows = {row.chat_id: row.level for row in result.scalars().all()}
        if chat_id in rows:
            return rows[chat_id]
        return rows.get(0, default)


# ── Warnings ─────────────────────────────────────────────────────────────
async def add_warning(chat_id: int, user_id: int, issued_by: int, reason: str | None) -> int:
    """Returns the user's total warning count in this chat after adding."""
    async with get_session() as session:
        session.add(
            Warning(chat_id=chat_id, user_id=user_id, issued_by=issued_by, reason=reason)
        )
        await session.flush()
        count = await session.scalar(
            select(func.count()).select_from(Warning).where(
                Warning.chat_id == chat_id, Warning.user_id == user_id
            )
        )
        return int(count or 0)


async def clear_warnings(chat_id: int, user_id: int) -> int:
    async with get_session() as session:
        result = await session.execute(
            delete(Warning).where(Warning.chat_id == chat_id, Warning.user_id == user_id)
        )
        return result.rowcount or 0


async def get_warning_count(chat_id: int, user_id: int) -> int:
    async with get_session() as session:
        count = await session.scalar(
            select(func.count()).select_from(Warning).where(
                Warning.chat_id == chat_id, Warning.user_id == user_id
            )
        )
        return int(count or 0)


# ── Notes ────────────────────────────────────────────────────────────────
async def save_note(
    chat_id: int,
    name: str,
    created_by: int,
    content_text: str | None = None,
    file_id: str | None = None,
    file_type: str | None = None,
    buttons_json: str | None = None,
) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(Note).where(Note.chat_id == chat_id, Note.name == name)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = Note(chat_id=chat_id, name=name, created_by=created_by)
            session.add(row)
        row.content_text = content_text
        row.file_id = file_id
        row.file_type = file_type
        row.buttons_json = buttons_json


async def get_note(chat_id: int, name: str) -> Note | None:
    async with get_session() as session:
        result = await session.execute(
            select(Note).where(Note.chat_id == chat_id, Note.name == name)
        )
        return result.scalar_one_or_none()


async def delete_note(chat_id: int, name: str) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(Note).where(Note.chat_id == chat_id, Note.name == name)
        )
        return (result.rowcount or 0) > 0


async def list_notes(chat_id: int) -> list[str]:
    async with get_session() as session:
        result = await session.execute(select(Note.name).where(Note.chat_id == chat_id))
        return sorted(result.scalars().all())


# ── Pinned info ──────────────────────────────────────────────────────────
async def save_pinned_info(
    chat_id: int, name: str, content_text: str, created_by: int, buttons_json: str | None = None
) -> PinnedInfo:
    async with get_session() as session:
        result = await session.execute(
            select(PinnedInfo).where(PinnedInfo.chat_id == chat_id, PinnedInfo.name == name)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = PinnedInfo(chat_id=chat_id, name=name, created_by=created_by, content_text=content_text)
            session.add(row)
        else:
            row.content_text = content_text
        row.buttons_json = buttons_json
        await session.flush()
        await session.refresh(row)
        return row


async def set_pinned_message_id(chat_id: int, name: str, message_id: int) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(PinnedInfo).where(PinnedInfo.chat_id == chat_id, PinnedInfo.name == name)
        )
        row = result.scalar_one_or_none()
        if row:
            row.message_id = message_id


async def get_pinned_info(chat_id: int, name: str) -> PinnedInfo | None:
    async with get_session() as session:
        result = await session.execute(
            select(PinnedInfo).where(PinnedInfo.chat_id == chat_id, PinnedInfo.name == name)
        )
        return result.scalar_one_or_none()


# ── Filters / blacklist / whitelist ─────────────────────────────────────
async def add_word_filter(chat_id: int, trigger: str, action: str, response_text: str | None) -> None:
    async with get_session() as session:
        session.add(
            WordFilter(chat_id=chat_id, trigger=trigger.lower(), action=action, response_text=response_text)
        )


async def remove_word_filter(chat_id: int, trigger: str) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(WordFilter).where(
                WordFilter.chat_id == chat_id, WordFilter.trigger == trigger.lower()
            )
        )
        return (result.rowcount or 0) > 0


async def list_word_filters(chat_id: int) -> list[WordFilter]:
    async with get_session() as session:
        result = await session.execute(select(WordFilter).where(WordFilter.chat_id == chat_id))
        return list(result.scalars().all())


async def add_list_entry(chat_id: int, list_type: str, value: str, added_by: int) -> None:
    async with get_session() as session:
        session.add(ListEntry(chat_id=chat_id, list_type=list_type, value=value, added_by=added_by))


async def remove_list_entry(chat_id: int, list_type: str, value: str) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(ListEntry).where(
                ListEntry.chat_id == chat_id,
                ListEntry.list_type == list_type,
                ListEntry.value == value,
            )
        )
        return (result.rowcount or 0) > 0


async def get_list(chat_id: int, list_type: str) -> list[str]:
    async with get_session() as session:
        result = await session.execute(
            select(ListEntry.value).where(
                ListEntry.chat_id == chat_id, ListEntry.list_type == list_type
            )
        )
        return list(result.scalars().all())


# ── Federation ───────────────────────────────────────────────────────────
async def create_federation(name: str, owner_id: int) -> Federation:
    async with get_session() as session:
        fed = Federation(name=name, owner_id=owner_id)
        session.add(fed)
        await session.flush()
        await session.refresh(fed)
        return fed


async def add_federation_admin(fed_id: int, user_id: int) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(FederationAdmin).where(
                FederationAdmin.fed_id == fed_id, FederationAdmin.user_id == user_id
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(FederationAdmin(fed_id=fed_id, user_id=user_id))


async def remove_federation_admin(fed_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(FederationAdmin).where(
                FederationAdmin.fed_id == fed_id, FederationAdmin.user_id == user_id
            )
        )
        return (result.rowcount or 0) > 0


async def link_chat_to_federation(fed_id: int, chat_id: int) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(FederationChat).where(
                FederationChat.fed_id == fed_id, FederationChat.chat_id == chat_id
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(FederationChat(fed_id=fed_id, chat_id=chat_id))


async def get_chat_federation_id(chat_id: int) -> int | None:
    async with get_session() as session:
        result = await session.execute(
            select(FederationChat.fed_id).where(FederationChat.chat_id == chat_id)
        )
        return result.scalar_one_or_none()


async def fban_user(fed_id: int, user_id: int, banned_by: int, reason: str | None) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(FederationBan).where(
                FederationBan.fed_id == fed_id, FederationBan.user_id == user_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                FederationBan(fed_id=fed_id, user_id=user_id, banned_by=banned_by, reason=reason)
            )


async def fun_ban_user(fed_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(FederationBan).where(
                FederationBan.fed_id == fed_id, FederationBan.user_id == user_id
            )
        )
        return (result.rowcount or 0) > 0


async def is_fbanned(fed_id: int, user_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(FederationBan).where(
                FederationBan.fed_id == fed_id, FederationBan.user_id == user_id
            )
        )
        return result.scalar_one_or_none() is not None


async def get_federation_chats(fed_id: int) -> list[int]:
    async with get_session() as session:
        result = await session.execute(
            select(FederationChat.chat_id).where(FederationChat.fed_id == fed_id)
        )
        return list(result.scalars().all())


# ── Music session (persisted settings only; live queue is in-memory) ────
async def get_or_create_music_session(chat_id: int) -> MusicSession:
    async with get_session() as session:
        row = await session.get(MusicSession, chat_id)
        if row is None:
            row = MusicSession(chat_id=chat_id)
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return row


async def update_music_session(chat_id: int, **fields) -> None:
    async with get_session() as session:
        row = await session.get(MusicSession, chat_id)
        if row is None:
            row = MusicSession(chat_id=chat_id)
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)


# ── Security events ──────────────────────────────────────────────────────
async def log_security_event(event_type: str, detail: str | None, chat_id: int | None = None) -> None:
    async with get_session() as session:
        session.add(SecurityEvent(event_type=event_type, detail=detail, chat_id=chat_id))
