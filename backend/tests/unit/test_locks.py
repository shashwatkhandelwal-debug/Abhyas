"""Unit tests for TeacherLockManager idle pruning and serialization (CHANGES 254f622 Item 11)."""

import asyncio
from uuid import uuid4

import pytest

from backend.app.core.locks import TeacherLockManager


@pytest.mark.asyncio
async def test_locks_pruning_when_idle() -> None:
    """Allocated per-teacher locks are pruned from registry when idle."""
    manager = TeacherLockManager()
    t1 = uuid4()
    t2 = uuid4()

    assert manager.active_lock_count() == 0

    # Acquire lock for t1
    async with manager.lock(t1):
        assert manager.active_lock_count() == 1
        # Acquire nested or second teacher lock
        async with manager.lock(t2):
            assert manager.active_lock_count() == 2

    # Both released: should be pruned back to 0
    assert manager.active_lock_count() == 0


@pytest.mark.asyncio
async def test_concurrent_locks_ref_counted_until_all_release() -> None:
    """When multiple tasks wait for the same teacher lock, lock is retained until all complete."""
    manager = TeacherLockManager()
    t_id = uuid4()
    events: list[str] = []

    async def worker(num: int, sleep_s: float) -> None:
        async with manager.lock(t_id):
            events.append(f"start_{num}")
            await asyncio.sleep(sleep_s)
            events.append(f"end_{num}")

    task1 = asyncio.create_task(worker(1, 0.05))
    task2 = asyncio.create_task(worker(2, 0.01))

    # Let tasks start and queue up
    await asyncio.sleep(0.01)
    # The lock should still be active
    assert manager.active_lock_count() == 1

    await asyncio.gather(task1, task2)

    # Serialized FIFO order preserved
    assert events == ["start_1", "end_1", "start_2", "end_2"]
    # Pruned after both tasks exit
    assert manager.active_lock_count() == 0
