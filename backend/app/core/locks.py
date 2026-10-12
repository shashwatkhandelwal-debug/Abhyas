"""Per-teacher asynchronous locks to prevent race conditions (spec/02 §2.5, T18, CHANGES 254f622 Item 11).

Serializes message processing per teacher so rapid concurrent inbounds (e.g. double-tapping
or rapid WhatsApp messages) are handled in FIFO order without corrupting state transitions.

Note: In-memory asyncio locks assume a single application instance (e.g., single Render web/worker
instance with concurrency 1 per teacher). If scaled horizontally across multiple server instances,
distributed locking (e.g., Redis or Postgres advisory locks) must be used.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID


class TeacherLockManager:
    """Registry of per-teacher asyncio locks with idle pruning (spec/02 §2.5)."""

    def __init__(self) -> None:
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._ref_counts: dict[UUID, int] = {}
        self._global_lock = asyncio.Lock()

    async def get_lock(self, teacher_id: UUID) -> asyncio.Lock:
        """Gets or creates an asyncio.Lock for the given teacher."""
        async with self._global_lock:
            if teacher_id not in self._locks:
                self._locks[teacher_id] = asyncio.Lock()
                self._ref_counts[teacher_id] = 0
            return self._locks[teacher_id]

    @asynccontextmanager
    async def lock(self, teacher_id: UUID) -> AsyncIterator[None]:
        """Async context manager acquiring the teacher's lock and pruning when idle."""
        async with self._global_lock:
            if teacher_id not in self._locks:
                self._locks[teacher_id] = asyncio.Lock()
                self._ref_counts[teacher_id] = 0
            self._ref_counts[teacher_id] += 1
            lock = self._locks[teacher_id]

        try:
            async with lock:
                yield
        finally:
            async with self._global_lock:
                self._ref_counts[teacher_id] -= 1
                if self._ref_counts[teacher_id] <= 0:
                    self._locks.pop(teacher_id, None)
                    self._ref_counts.pop(teacher_id, None)

    def active_lock_count(self) -> int:
        """Returns the number of allocated teacher locks."""
        return len(self._locks)

    def clear(self) -> None:
        """Clears all locks (for test isolation)."""
        self._locks.clear()
        self._ref_counts.clear()


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
