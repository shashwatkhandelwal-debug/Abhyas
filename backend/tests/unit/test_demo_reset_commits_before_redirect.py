"""The login/logout demo reset must be committed before the response is sent.

The session dependency commits only after the response has gone out, so without an explicit commit
the browser's next request (the 303 target) can read the rows from before the reset. Measured on a
live seeded server: 17 of 25 immediate re-logins saw the old state (the chat instead of the Start
here screen); with the commit 0 of 25.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.auth.router import _reset_demo_teacher


def _db(events: list[str]) -> Any:
    db = MagicMock()
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(side_effect=lambda: events.append("begin_nested"))
    nested.__aexit__ = AsyncMock(side_effect=lambda *a: events.append("end_nested") or False)
    db.begin_nested.return_value = nested
    db.commit = AsyncMock(side_effect=lambda: events.append("commit"))
    return db


def _user(demo: bool = True, role: str = "teacher") -> Any:
    return SimpleNamespace(is_demo=demo, role=role, username="teacher.demo1")


@pytest.mark.asyncio
@pytest.mark.parametrize("on_login", [True, False])
async def test_the_reset_is_committed_after_it_runs(on_login: bool) -> None:
    events: list[str] = []

    async def fake_reset(*_a: Any, **_k: Any) -> bool:
        events.append("reset")
        return True

    with (
        patch("backend.app.db.seed.reset_demo_teacher", fake_reset),
        patch("backend.app.db.seed.reset_demo_teacher_unless_fresh", fake_reset),
    ):
        await _reset_demo_teacher(_db(events), _user(), on_login=on_login)
    assert events == ["begin_nested", "reset", "end_nested", "commit"]


@pytest.mark.asyncio
async def test_no_commit_for_a_real_teacher_or_a_non_teacher() -> None:
    events: list[str] = []
    await _reset_demo_teacher(_db(events), _user(demo=False), on_login=True)
    await _reset_demo_teacher(_db(events), _user(role="admin"), on_login=True)
    await _reset_demo_teacher(_db(events), None, on_login=True)
    assert events == []


@pytest.mark.asyncio
async def test_a_failing_reset_never_blocks_login_and_is_not_committed() -> None:
    events: list[str] = []

    async def boom(*_a: Any, **_k: Any) -> bool:
        raise RuntimeError("db down")

    with patch("backend.app.db.seed.reset_demo_teacher_unless_fresh", boom):
        await _reset_demo_teacher(_db(events), _user(), on_login=True)  # must not raise
    assert "commit" not in events
