from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database.engine import init_db
from bot.handlers import (
    bot_protection as _bot_protection,  # noqa: F401 — imported for its functions, not a router
)
from bot.handlers import (
    cleanup,
    federation,
    guard,
    help as help_router,
    member_events,
    moderation,
    notes,
    owner,
    pinned,
    welcome,
)
from bot.utils.security import verify_owner_configuration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot.main")

# Registration order matters: security/owner and moderation commands are
# registered before the catch-all content guard, so a command is always
# matched by its own handler first. member_events is the single
# chat_member dispatch point (see its module docstring).
ROUTERS = (
    owner.router,
    moderation.router,
    welcome.router,
    member_events.router,
    notes.router,
    pinned.router,
    federation.router,
    cleanup.router,
    # Music is included below only when ENABLE_MUSIC=true.
    help_router.router,
    guard.router,  # must stay last — it's the catch-all for plain messages
)


async def main() -> None:
    await verify_owner_configuration()
    await init_db()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    for router in ROUTERS:
        dp.include_router(router)

    if settings.enable_music:
        from bot.music import handlers as music_handlers
        from bot.music.userbot import start_userbot, stop_userbot

        if not settings.userbot_session_string:
            raise RuntimeError(
                "ENABLE_MUSIC=true requires USERBOT_SESSION_STRING on a server. "
                "Generate it locally with: python -m bot.music.generate_session"
            )
        dp.include_router(music_handlers.router)
        await start_userbot()
        music_handlers.register_stream_end_handler()

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting polling…")
        await dp.start_polling(bot)
    finally:
        if settings.enable_music:
            await stop_userbot()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")
