"""
Central configuration. Every secret comes from the environment — never
hard-code a token, API hash, or DB credential here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _int_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(default_factory=lambda: _require("BOT_TOKEN"))
    owner_id: int = field(default_factory=lambda: int(_require("OWNER_ID")))

    api_id: int = field(default_factory=lambda: int(os.getenv("API_ID", "0")))
    api_hash: str = field(default_factory=lambda: os.getenv("API_HASH", ""))
    userbot_session_string: str = field(
        default_factory=lambda: os.getenv("USERBOT_SESSION_STRING", "")
    )
    enable_music: bool = field(
        default_factory=lambda: os.getenv("ENABLE_MUSIC", "false").strip().lower() in {"1", "true", "yes", "on"}
    )

    database_url: str = field(default_factory=lambda: _require("DATABASE_URL"))

    log_chat_id: int | None = field(
        default_factory=lambda: (
            int(v) if (v := os.getenv("LOG_CHAT_ID")) else None
        )
    )

    extra_trusted_admin_ids: list[int] = field(
        default_factory=lambda: _int_list(os.getenv("EXTRA_TRUSTED_ADMIN_IDS"))
    )


settings = Settings()

# Cloud providers commonly expose PostgreSQL URLs as postgres:// or postgresql://.
# SQLAlchemy asyncpg needs the explicit postgresql+asyncpg:// driver.
if settings.database_url.startswith("postgres://"):
    object.__setattr__(settings, "database_url", "postgresql+asyncpg://" + settings.database_url[len("postgres://"):])
elif settings.database_url.startswith("postgresql://"):
    object.__setattr__(settings, "database_url", "postgresql+asyncpg://" + settings.database_url[len("postgresql://"):])
