from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class Track:
    title: str
    artist: str | None
    duration_seconds: int | None
    stream_url: str
    requested_by: int
    query: str


@dataclass
class ChatQueue:
    current: Track | None = None
    upcoming: list[Track] = field(default_factory=list)
    loop_mode: str = "off"  # off | track | queue
    volume: int = 100
    paused: bool = False

    def add(self, track: Track) -> int:
        self.upcoming.append(track)
        return len(self.upcoming)

    def pop_next(self) -> Track | None:
        """Advances the queue, honoring loop mode. Returns the new current track."""
        if self.loop_mode == "track" and self.current is not None:
            return self.current

        if self.loop_mode == "queue" and self.current is not None:
            self.upcoming.append(self.current)

        if not self.upcoming:
            self.current = None
            return None

        self.current = self.upcoming.pop(0)
        return self.current

    def remove(self, index_1_based: int) -> Track | None:
        idx = index_1_based - 1
        if 0 <= idx < len(self.upcoming):
            return self.upcoming.pop(idx)
        return None

    def move(self, from_1_based: int, to_1_based: int) -> bool:
        from_idx, to_idx = from_1_based - 1, to_1_based - 1
        if not (0 <= from_idx < len(self.upcoming) and 0 <= to_idx < len(self.upcoming)):
            return False
        track = self.upcoming.pop(from_idx)
        self.upcoming.insert(to_idx, track)
        return True

    def shuffle(self) -> None:
        random.shuffle(self.upcoming)

    def clear(self) -> None:
        self.upcoming.clear()
        self.current = None


class QueueRegistry:
    """In-memory registry, one ChatQueue per chat. Live playback state is
    intentionally not persisted — a restart should require re-queuing,
    which is safer than resuming a stream into a voice chat blind."""

    def __init__(self) -> None:
        self._queues: dict[int, ChatQueue] = {}

    def get(self, chat_id: int) -> ChatQueue:
        if chat_id not in self._queues:
            self._queues[chat_id] = ChatQueue()
        return self._queues[chat_id]

    def drop(self, chat_id: int) -> None:
        self._queues.pop(chat_id, None)


registry = QueueRegistry()
