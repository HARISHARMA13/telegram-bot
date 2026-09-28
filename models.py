"""
All persistent state lives here. One row per (chat, concern) so that the
bot is fully multi-group and survives restarts with zero config loss.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class PermissionLevel(str, enum.Enum):
    OWNER_ONLY = "owner_only"
    OWNER_TRUSTED = "owner_trusted"
    GROUP_ADMIN = "group_admin"
    ALL_MEMBERS = "all_members"


# ── Per-group configuration ────────────────────────────────────────────
class GroupConfig(Base):
    __tablename__ = "group_config"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Welcome
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_autodelete_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Join requests
    auto_approve_join_requests: Mapped[bool] = mapped_column(Boolean, default=False)
    log_join_requests: Mapped[bool] = mapped_column(Boolean, default=True)

    # Moderation locks (media/links/stickers/gifs/forwards)
    lock_media: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_links: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_stickers: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_gifs: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_forwards: Mapped[bool] = mapped_column(Boolean, default=False)

    # Anti-spam / anti-flood
    antiflood_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    antiflood_max_messages: Mapped[int] = mapped_column(Integer, default=6)
    antiflood_window_seconds: Mapped[int] = mapped_column(Integer, default=8)
    antiflood_action: Mapped[str] = mapped_column(String(20), default="mute")  # mute|kick|ban

    # Warnings
    warn_limit: Mapped[int] = mapped_column(Integer, default=3)
    warn_action: Mapped[str] = mapped_column(String(20), default="mute")  # mute|kick|ban

    # Slow mode (informational — actual enforcement needs Telegram's native
    # slow-mode set via chat permissions where the Bot API allows it)
    slowmode_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Cleanup toggles, stored as a bitmask-ish JSON blob for flexibility
    cleanup_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Music
    music_restricted_to_admins: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Owner / trusted admins (global, not per-group, per the spec: one
#    permanent Owner, plus Owner-controlled Trusted Admins) ────────────
class TrustedAdmin(Base):
    __tablename__ = "trusted_admins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_by: Mapped[int] = mapped_column(BigInteger)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TrustedBot(Base):
    __tablename__ = "trusted_bots"

    bot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_by: Mapped[int] = mapped_column(BigInteger)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Per-command permission overrides ───────────────────────────────────
class CommandPermission(Base):
    __tablename__ = "command_permissions"
    __table_args__ = (UniqueConstraint("chat_id", "command", name="uq_chat_command"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)  # 0 = global default
    command: Mapped[str] = mapped_column(String(64))
    level: Mapped[PermissionLevel] = mapped_column(Enum(PermissionLevel))


# ── Warnings ────────────────────────────────────────────────────────────
class Warning(Base):
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_by: Mapped[int] = mapped_column(BigInteger)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Notes ───────────────────────────────────────────────────────────────
class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (UniqueConstraint("chat_id", "name", name="uq_chat_note_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(128))
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # photo|video|doc|...
    buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Pinned info messages (rules/announcements with inline buttons) ─────
class PinnedInfo(Base):
    __tablename__ = "pinned_info"
    __table_args__ = (UniqueConstraint("chat_id", "name", name="uq_chat_pinned_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(128))
    content_text: Mapped[str] = mapped_column(Text)
    buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Filters / blacklist / whitelist ────────────────────────────────────
class WordFilter(Base):
    __tablename__ = "word_filters"
    __table_args__ = (UniqueConstraint("chat_id", "trigger", name="uq_chat_trigger"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    trigger: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(20), default="delete")  # delete|warn|mute|ban
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ListEntry(Base):
    """Generic blacklist/whitelist entry, scoped per chat."""

    __tablename__ = "list_entries"
    __table_args__ = (
        UniqueConstraint("chat_id", "list_type", "value", name="uq_chat_list_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    list_type: Mapped[str] = mapped_column(String(16))  # "blacklist" | "whitelist"
    value: Mapped[str] = mapped_column(String(255))
    added_by: Mapped[int] = mapped_column(BigInteger)


# ── Federation (global-ban network) ─────────────────────────────────────
class Federation(Base):
    __tablename__ = "federations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    owner_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FederationAdmin(Base):
    __tablename__ = "federation_admins"
    __table_args__ = (UniqueConstraint("fed_id", "user_id", name="uq_fed_admin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fed_id: Mapped[int] = mapped_column(ForeignKey("federations.id"))
    user_id: Mapped[int] = mapped_column(BigInteger)


class FederationChat(Base):
    __tablename__ = "federation_chats"
    __table_args__ = (UniqueConstraint("fed_id", "chat_id", name="uq_fed_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fed_id: Mapped[int] = mapped_column(ForeignKey("federations.id"))
    chat_id: Mapped[int] = mapped_column(BigInteger)


class FederationBan(Base):
    __tablename__ = "federation_bans"
    __table_args__ = (UniqueConstraint("fed_id", "user_id", name="uq_fed_ban"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fed_id: Mapped[int] = mapped_column(ForeignKey("federations.id"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banned_by: Mapped[int] = mapped_column(BigInteger)
    banned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Music settings / persisted queue snapshot (so a restart can at least
#    show what was playing; live playback state is kept in memory) ─────
class MusicSession(Base):
    __tablename__ = "music_sessions"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    volume: Mapped[int] = mapped_column(Integer, default=100)
    loop_mode: Mapped[str] = mapped_column(String(16), default="off")  # off|track|queue
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Security event log (also mirrored to the log channel if configured)
class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
