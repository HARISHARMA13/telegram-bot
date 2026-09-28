"""
Resolves a search query or URL into a playable audio stream.

Uses yt-dlp against sources that are legally and technically accessible
(e.g. a platform's public streams). This module deliberately does NOT
download or persist copies of copyrighted media to disk — it only
extracts a temporary, direct stream URL for PyTgCalls to pipe into the
voice chat. Operators are responsible for using this only with content
they're licensed/permitted to play in their community, and for complying
with the terms of whatever source they configure yt-dlp against.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import yt_dlp

_YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}


@dataclass
class ResolvedTrack:
    title: str
    artist: str | None
    duration_seconds: int | None
    stream_url: str


async def resolve(query: str) -> ResolvedTrack | None:
    """
    Accepts either a direct URL or a free-text search query (in which case
    it searches and takes the first result — swap `default_search` above
    or add a dedicated search backend if you want different behavior).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _resolve_sync, query)


def _resolve_sync(query: str) -> ResolvedTrack | None:
    search_query = query if _looks_like_url(query) else f"ytsearch1:{query}"
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(search_query, download=False)
        if info is None:
            return None
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                return None
            info = entries[0]

        stream_url = info.get("url")
        if not stream_url:
            # Some extractors nest formats; fall back to the best audio format's URL.
            formats = info.get("formats") or []
            audio_formats = [f for f in formats if f.get("acodec") != "none"]
            if not audio_formats:
                return None
            stream_url = audio_formats[-1]["url"]

        return ResolvedTrack(
            title=info.get("title", query),
            artist=info.get("artist") or info.get("uploader"),
            duration_seconds=info.get("duration"),
            stream_url=stream_url,
        )


def _looks_like_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")
