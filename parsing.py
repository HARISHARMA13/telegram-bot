from __future__ import annotations

import datetime as dt
import re

from aiogram.filters import CommandObject
from aiogram.types import Message

_DURATION_RE = re.compile(r"^(\d+)([smhdw])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(token: str) -> dt.timedelta | None:
    match = _DURATION_RE.match(token.strip())
    if not match:
        return None
    amount, unit = match.groups()
    return dt.timedelta(seconds=int(amount) * _UNIT_SECONDS[unit.lower()])


async def resolve_target(
    message: Message, command: CommandObject
) -> tuple[int | None, str | None]:
    """
    Returns (user_id, remaining_args_text). Supports replying to a user,
    or passing a numeric ID / @username as the first argument.
    """
    args = command.args or ""

    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id, args.strip()

    parts = args.split(maxsplit=1)
    if not parts:
        return None, None

    first, rest = parts[0], (parts[1] if len(parts) > 1 else "")

    if first.lstrip("-").isdigit():
        return int(first), rest

    if first.startswith("@"):
        try:
            chat_member = await message.bot.get_chat(first)
            return chat_member.id, rest
        except Exception:  # noqa: BLE001
            return None, None

    return None, None
