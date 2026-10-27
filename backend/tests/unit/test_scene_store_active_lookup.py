"""PostgresSceneStore.get_active_for_teacher: Postgres is the truth when it answers.

If the DB is reachable and has no active scene for the teacher, the store must say so. The
in-process cache is only a fallback for an unreachable or unconfigured DB; consulting it after a
successful "no active row" answer would resurrect a scene a demo reset (or another worker)
already ended or deleted.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any
from uuid import uuid4

import pytest

from backend.app.config import settings
from backend.app.rehearsal import scene_store as ss
from backend.app.rehearsal.scene_runner import SceneRunner
from backend.app.rehearsal.scene_store import InMemorySceneStore, PostgresSceneStore


class _NoActiveRowResult:
    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(
        self, et: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None

    async def execute(self, _stmt: Any) -> _NoActiveRowResult:
        return _NoActiveRowResult()


class _BrokenSession(_FakeSession):
    async def execute(self, _stmt: Any) -> _NoActiveRowResult:
        raise ConnectionError("db down")


async def _store_with_cached_active_scene() -> tuple[PostgresSceneStore, Any]:
    teacher_id = uuid4()
    record = await SceneRunner(store=InMemorySceneStore()).create_scene(
        teacher_id, "NUM_SUB_REGROUP_BUNDLES"
    )
    store = PostgresSceneStore()
    store._memory.save_sync(record)
    assert record.active
    return store, teacher_id


@pytest.mark.asyncio
async def test_db_answers_no_active_scene_so_cached_active_scene_is_not_resurrected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://x/y")
    monkeypatch.setattr(ss, "async_session_factory", lambda: _FakeSession())
    store, teacher_id = await _store_with_cached_active_scene()
    assert await store.get_active_for_teacher(teacher_id) is None


@pytest.mark.asyncio
async def test_unreachable_db_still_falls_back_to_the_cached_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://x/y")
    monkeypatch.setattr(ss, "async_session_factory", lambda: _BrokenSession())
    store, teacher_id = await _store_with_cached_active_scene()
    found = await store.get_active_for_teacher(teacher_id)
    assert found is not None and found.teacher_id == teacher_id
