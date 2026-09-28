"""
Run once, interactively, to generate a session string for the music
userbot: `python -m bot.music.generate_session`

It will prompt for the phone number, login code, and (if enabled) 2FA
password of the REAL Telegram account you want to use as the voice-chat
assistant — this should generally be a dedicated account, not your
personal one. The resulting string is printed to your terminal ONCE;
copy it straight into USERBOT_SESSION_STRING in your .env and never
share or commit it — it grants full access to that account.
"""
from __future__ import annotations

import asyncio

from pyrogram import Client

from bot.config import settings


async def main() -> None:
    async with Client("assistant_setup", api_id=settings.api_id, api_hash=settings.api_hash) as client:
        session_string = await client.export_session_string()
        print("\n" + "=" * 60)
        print("Copy this into USERBOT_SESSION_STRING in your .env:")
        print(session_string)
        print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
