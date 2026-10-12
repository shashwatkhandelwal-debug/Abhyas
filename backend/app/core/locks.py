"""Per-teacher asynchronous locks to prevent race conditions (spec/02 §2.5, T18).

Serializes message processing per teacher so rapid concurrent inbounds (e.g. double-tapping
or rapid WhatsApp messages) are handled in FIFO order without corrupting state transitions.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID


class TeacherLockManager:
    """Registry of per-teacher asyncio locks."""

    def __init__(self) -> None:
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get_lock(self, teacher_id: UUID) -> asyncio.Lock:
        """Gets or creates an asyncio.Lock for the given teacher."""
        if teacher_id not in self._locks:
            async with self._global_lock:
                if teacher_id not in self._locks:
                    self._locks[teacher_id] = asyncio.Lock()
        return self._locks[teacher_id]

    @asynccontextmanager
    async def lock(self, teacher_id: UUID) -> AsyncIterator[None]:
        """Async context manager acquiring the teacher's lock."""
        lock = await self.get_lock(teacher_id)
        async with lock:
            yield

    def active_lock_count(self) -> int:
        """Returns the number of allocated teacher locks."""
        return len(self._locks)

    def clear(self) -> None:
        """Clears all locks (for test isolation)."""
        self._locks.clear()


# Global singleton instance
teacher_locks = TeacherLockManager()


def teacher_lock(teacher_id: UUID) -> AbstractAsyncContextManager[None]:
    """Helper context manager to acquire a lock for a teacher."""
    return teacher_locks.lock(teacher_id)


__all__ = [
    "TeacherLockManager",
    "teacher_locks",
    "teacher_lock",
]
