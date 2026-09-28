"""
User-facing /play /pause /resume /skip /stop /queue etc. These run on the
regular aiogram bot; under the hood they drive the Pyrogram userbot +
PyTgCalls instance defined in userbot.py.

NOTE ON PyTgCalls VERSIONS: py-tgcalls's API has changed across releases
(MediaStream vs. the older AudioPiped helpers). This targets py-tgcalls
2.x (`from pytgcalls.types import MediaStream`). If you pin a different
version, adjust `_start_stream` / `_change_stream` accordingly — check
https://github.com/pytgcalls/pytgcalls for the version you install.
"""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from pytgcalls.exceptions import NoActiveGroupCall
from pytgcalls.types import MediaStream

from bot.database import crud
from bot.music.queue import Track, registry
from bot.music.source import resolve
from bot.music.userbot import call_py
from bot.utils.filters import IsGroupAdminOrHigher
from bot.utils.logger_service import log_action

router = Router(name="music")


async def _music_allowed(message: Message) -> bool:
    cfg = await crud.get_or_create_group_config(message.chat.id, message.chat.title)
    if not cfg.music_restricted_to_admins:
        return True
    return await IsGroupAdminOrHigher()(message)


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "live/unknown"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"


async def _start_stream(chat_id: int, track: Track) -> None:
    stream = MediaStream(track.stream_url)
    try:
        await call_py.play(chat_id, stream)
    except NoActiveGroupCall:
        raise RuntimeError(
            "There's no active voice chat in this group — start one first, then /play again."
        )


async def _advance_or_leave(bot: Bot | None, chat_id: int) -> None:
    queue = registry.get(chat_id)
    next_track = queue.pop_next()
    if next_track is None:
        try:
            await call_py.leave_call(chat_id)
        except Exception:  # noqa: BLE001
            pass
        return
    await _start_stream(chat_id, next_track)
    if bot is not None:
        await log_action(bot, chat_id, "music", f"now playing: {next_track.title}")


@router.message(Command("play"))
async def cmd_play(message: Message, command: CommandObject, bot: Bot) -> None:
    if not await _music_allowed(message):
        await message.reply("Music playback is restricted to admins in this group.")
        return
    if not command.args:
        await message.reply("Usage: /play <song name or URL>")
        return

    status = await message.reply("🔎 Searching…")
    resolved = await resolve(command.args)
    if resolved is None:
        await status.edit_text("Couldn't find anything for that query.")
        return

    queue = registry.get(message.chat.id)
    track = Track(
        title=resolved.title,
        artist=resolved.artist,
        duration_seconds=resolved.duration_seconds,
        stream_url=resolved.stream_url,
        requested_by=message.from_user.id,
        query=command.args,
    )

    if queue.current is None:
        queue.current = track
        try:
            await _start_stream(message.chat.id, track)
        except RuntimeError as exc:
            queue.current = None
            await status.edit_text(str(exc))
            return
        await status.edit_text(f"▶️ Now playing: <b>{track.title}</b> ({_format_duration(track.duration_seconds)})", parse_mode="HTML")
        await log_action(bot, message.chat.id, "music", f"{message.from_user.id} started: {track.title}")
    else:
        position = queue.add(track)
        await status.edit_text(f"➕ Queued at position {position}: <b>{track.title}</b>", parse_mode="HTML")


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.reply("Usage: /search <song name>")
        return
    resolved = await resolve(command.args)
    if resolved is None:
        await message.reply("No results found.")
        return
    await message.reply(
        f"🎵 <b>{resolved.title}</b>\n"
        f"Artist: {resolved.artist or 'unknown'}\n"
        f"Duration: {_format_duration(resolved.duration_seconds)}\n\n"
        f"Use /play {command.args} to queue it.",
        parse_mode="HTML",
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    if not await _music_allowed(message):
        return
    queue = registry.get(message.chat.id)
    if queue.current is None:
        await message.reply("Nothing is playing.")
        return
    await call_py.pause(message.chat.id)
    queue.paused = True
    await message.reply("⏸ Paused.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    if not await _music_allowed(message):
        return
    queue = registry.get(message.chat.id)
    if queue.current is None:
        await message.reply("Nothing is playing.")
        return
    await call_py.resume(message.chat.id)
    queue.paused = False
    await message.reply("▶️ Resumed.")


@router.message(Command("skip"))
async def cmd_skip(message: Message, bot: Bot) -> None:
    if not await _music_allowed(message):
        return
    queue = registry.get(message.chat.id)
    if queue.current is None:
        await message.reply("Nothing is playing.")
        return
    skipped = queue.current
    await _advance_or_leave(bot, message.chat.id)
    new_current = registry.get(message.chat.id).current
    await message.reply(
        f"⏭ Skipped <b>{skipped.title}</b>." + (f" Now playing <b>{new_current.title}</b>." if new_current else " Queue is empty.")
        , parse_mode="HTML",
    )


@router.message(Command("stop"))
async def cmd_stop(message: Message, bot: Bot) -> None:
    if not await _music_allowed(message):
        return
    registry.get(message.chat.id).clear()
    try:
        await call_py.leave_call(message.chat.id)
    except Exception:  # noqa: BLE001
        pass
    await log_action(bot, message.chat.id, "music", f"{message.from_user.id} stopped playback")
    await message.reply("⏹ Stopped and cleared the queue.")


@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    queue = registry.get(message.chat.id)
    if queue.current is None:
        await message.reply("Nothing is playing and the queue is empty.")
        return
    lines = [f"▶️ Now: <b>{queue.current.title}</b> ({_format_duration(queue.current.duration_seconds)})"]
    for i, track in enumerate(queue.upcoming, start=1):
        lines.append(f"{i}. {track.title} ({_format_duration(track.duration_seconds)})")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("nowplaying"))
async def cmd_nowplaying(message: Message) -> None:
    queue = registry.get(message.chat.id)
    if queue.current is None:
        await message.reply("Nothing is playing.")
        return
    t = queue.current
    await message.reply(
        f"▶️ <b>{t.title}</b>\nArtist: {t.artist or 'unknown'}\nDuration: {_format_duration(t.duration_seconds)}\n"
        f"Requested by: <code>{t.requested_by}</code>",
        parse_mode="HTML",
    )


@router.message(Command("shuffle"))
async def cmd_shuffle(message: Message) -> None:
    if not await _music_allowed(message):
        return
    registry.get(message.chat.id).shuffle()
    await message.reply("🔀 Queue shuffled.")


@router.message(Command("remove"))
async def cmd_remove(message: Message, command: CommandObject) -> None:
    if not await _music_allowed(message):
        return
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /remove <queue position>")
        return
    removed = registry.get(message.chat.id).remove(int(command.args))
    await message.reply(f"✅ Removed: {removed.title}" if removed else "No track at that position.")


@router.message(Command("move"))
async def cmd_move(message: Message, command: CommandObject) -> None:
    if not await _music_allowed(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await message.reply("Usage: /move <from_position> <to_position>")
        return
    ok = registry.get(message.chat.id).move(int(parts[0]), int(parts[1]))
    await message.reply("✅ Moved." if ok else "Invalid positions.")


@router.message(Command("volume"))
async def cmd_volume(message: Message, command: CommandObject) -> None:
    if not await _music_allowed(message):
        return
    if not (command.args and command.args.isdigit()):
        await message.reply("Usage: /volume <0-200>")
        return
    level = max(0, min(200, int(command.args)))
    queue = registry.get(message.chat.id)
    queue.volume = level
    try:
        await call_py.change_volume_call(message.chat.id, level)
    except Exception:  # noqa: BLE001
        pass
    await crud.update_music_session(message.chat.id, volume=level)
    await message.reply(f"🔊 Volume set to {level}.")


@router.message(Command("loop"))
async def cmd_loop(message: Message, command: CommandObject) -> None:
    if not await _music_allowed(message):
        return
    mode = (command.args or "").strip().lower()
    if mode not in ("off", "track", "queue"):
        await message.reply("Usage: /loop off|track|queue")
        return
    queue = registry.get(message.chat.id)
    queue.loop_mode = mode
    await crud.update_music_session(message.chat.id, loop_mode=mode)
    await message.reply(f"🔁 Loop mode: {mode}")


def register_stream_end_handler() -> None:
    """
    Wires PyTgCalls' stream-ended event to auto-advance the queue. Call
    once at startup (see main.py). Kept as a function so it can bind
    against the shared `call_py` instance without import-order issues.
    """

    @call_py.on_stream_end()
    async def _on_stream_end(_, update) -> None:  # noqa: ANN001 — pytgcalls callback signature
        await _advance_or_leave(None, update.chat_id)
