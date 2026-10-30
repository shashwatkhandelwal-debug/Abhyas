"""L2: "what worked for other teachers" (flag PEER_WORKED_ENABLED): counts, scope fallback, the
n<10 rule, consent, Hindi and English, flag off. A fake repository holds the follow-up answers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from test_class_checkin import Teacher, alltext, ids
from test_followup import FRIDAY, Clock, at, check_in, due_and_offered

from backend.app.class_profile import checkin_flow, followup, peer_worked
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.sessions.titles import move_title

STRUGGLE = "NUM_SUB_REGROUP"
MOVE = "NUM_SUB_REGROUP_BUNDLES"
N = settings.AGGREGATION_SUPPRESSION_N
DASHES = ("—", "–")


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> Clock:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "FOLLOWUP_ENABLED", True)
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", True)
    monkeypatch.setattr(settings, "PEER_WORKED_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    clock = Clock(at(FRIDAY))
    monkeypatch.setattr(followup, "utcnow", clock)
    return clock


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


Row = tuple[UUID, str, datetime, bool, bool, str | None]


def worked(
    count: int,
    *,
    cluster: str | None = "KNP-C01",
    consent: bool = True,
    demo: bool = False,
    days_ago: int = 3,
    struggle: str = STRUGGLE,
) -> list[Row]:
    when = at(FRIDAY) - timedelta(days=days_ago)
    return [(uuid4(), struggle, when, consent, demo, cluster) for _ in range(count)]


def line(n: int) -> str:
    return get_message("pw_line", n=n, move=move_title(MOVE))


async def stuck_text(t: Teacher, flags: Clock, rows: list[Row]) -> str:
    flags.moment = at(FRIDAY)  # a fresh Friday for every teacher
    t.repo._peer_worked = rows  # type: ignore[attr-defined]
    await due_and_offered(t, flags)
    return alltext(await t.tap(followup.BTN_STUCK))


async def new_teacher(cluster: str | None = "KNP-C01") -> Teacher:
    t = await Teacher("demo3", "f").setup()
    row = await t.repo.get_or_create_teacher(t.teacher_id)
    row.cluster_id = cluster
    return t


# ── the pure scope rule ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("n_cluster", "n_all", "expected"),
    [
        (N, N + 5, N),  # the cluster reaches the limit: the cluster's count
        (N + 3, N + 3, N + 3),
        (N - 1, N, N),  # the cluster is below it: everyone's count
        (None, N + 2, N + 2),  # no cluster known
        (N - 1, N - 1, None),  # nothing reaches it: no line at all
        (0, 0, None),
        (None, 0, None),
    ],
)
def test_scope_rule(n_cluster: int | None, n_all: int, expected: int | None) -> None:
    assert peer_worked.choose_scope(n_cluster, n_all) == expected


@pytest.mark.asyncio
async def test_peer_line_asks_for_all_only_when_the_cluster_is_too_small() -> None:
    calls: list[str | None] = []

    async def count(cluster: str | None) -> int:
        calls.append(cluster)
        return {"C1": N, None: N + 4}[cluster]

    assert await peer_worked.peer_line(STRUGGLE, cluster_id="C1", count=count) == line(N)
    assert calls == ["C1"]


@pytest.mark.asyncio
async def test_a_struggle_without_a_move_has_no_line() -> None:
    async def count(cluster: str | None) -> int:
        return 99

    assert await peer_worked.peer_line("NUM_COUNTING", cluster_id=None, count=count) is None
    assert await peer_worked.peer_line(None, cluster_id=None, count=count) is None
    assert await peer_worked.peer_line("NOT_A_STRUGGLE", cluster_id=None, count=count) is None


# ── after "still stuck" ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stuck_shows_the_cluster_count_with_the_move_name(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    text = await stuck_text(t, flags, worked(N + 2))
    assert line(N + 2) in text
    assert move_title(MOVE) in text and str(N + 2) in text
    if lang == "hi":
        assert f"इस दिक्कत में {N + 2} शिक्षकों ने बताया कि" in text


@pytest.mark.asyncio
async def test_the_line_comes_before_the_buttons_never_last(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    t.repo._peer_worked = worked(N)  # type: ignore[attr-defined]
    await due_and_offered(t, flags)
    out = await t.tap(followup.BTN_STUCK)
    assert out[-1].buttons and line(N) not in (out[-1].text_hi or "")
    assert any(line(N) in (m.text_hi or "") for m in out[:-1])
    assert followup.BTN_PRACTICE in ids(out)


@pytest.mark.asyncio
async def test_a_small_cluster_falls_back_to_all_teachers(lang: str, flags: Clock) -> None:
    t = await new_teacher("KNP-C01")
    rows = worked(N - 4, cluster="KNP-C01") + worked(7, cluster="KNP-C02")
    assert line(N + 3) in await stuck_text(t, flags, rows)


@pytest.mark.asyncio
async def test_a_teacher_without_a_cluster_uses_all_teachers(lang: str, flags: Clock) -> None:
    t = await new_teacher(None)
    assert line(N) in await stuck_text(t, flags, worked(N, cluster="KNP-C02"))


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, N - 1])
async def test_fewer_than_ten_leaves_the_line_out_entirely(
    lang: str, flags: Clock, count: int
) -> None:
    t = await new_teacher()
    text = await stuck_text(t, flags, worked(count))
    assert get_message("pw_line", n=count, move=move_title(MOVE)) not in text
    assert "शिक्षकों ने बताया" not in text and "teachers said" not in text


@pytest.mark.asyncio
async def test_only_consenting_teachers_are_counted(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    rows = worked(N - 1) + worked(6, consent=False)  # nine consent, six do not
    out = await stuck_text(t, flags, rows)
    assert "शिक्षकों ने बताया" not in out and "teachers said" not in out
    t2 = await new_teacher()
    out = await stuck_text(t2, flags, worked(N) + worked(6, consent=False))
    assert line(N) in out  # the six who did not consent are not in the number


@pytest.mark.asyncio
async def test_only_the_last_sixty_days_and_only_this_struggle(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    rows = (
        worked(N, days_ago=settings.PEER_WORKED_WINDOW_DAYS + 5)  # too old
        + worked(N, struggle="NUM_ADD_CARRY")  # another struggle
    )
    out = await stuck_text(t, flags, rows)
    assert "शिक्षकों ने बताया" not in out and "teachers said" not in out
    t2 = await new_teacher()
    fresh = worked(N, days_ago=settings.PEER_WORKED_WINDOW_DAYS - 1)
    assert line(N) in await stuck_text(t2, flags, fresh)


@pytest.mark.asyncio
async def test_demo_and_real_teachers_are_never_mixed(lang: str, flags: Clock) -> None:
    t = await new_teacher()  # a real teacher
    out = await stuck_text(t, flags, worked(N + 5, demo=True))
    assert "शिक्षकों ने बताया" not in out and "teachers said" not in out


@pytest.mark.asyncio
async def test_she_is_not_counted_among_the_others(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    mine = (t.teacher_id, STRUGGLE, at(FRIDAY) - timedelta(days=2), True, False, "KNP-C01")
    out = await stuck_text(t, flags, [*worked(N - 1), mine])
    assert "शिक्षकों ने बताया" not in out and "teachers said" not in out


@pytest.mark.asyncio
async def test_names_and_schools_never_appear(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    text = await stuck_text(t, flags, worked(N))
    assert "KNP" not in text and "SCH" not in text


# ── "could not try" and the check-in tip ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_could_not_try_shows_it_after_the_reason_not_before(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    t.repo._peer_worked = worked(N)  # type: ignore[attr-defined]
    await due_and_offered(t, flags)
    asked = await t.tap(followup.BTN_CANT)
    assert line(N) not in alltext(asked)  # the reason question comes first
    out = await t.tap(f"{followup.WHY_PREFIX}time")
    assert line(N) in alltext(out) and out[-1].buttons


@pytest.mark.asyncio
async def test_worked_answer_does_not_show_it(lang: str, flags: Clock) -> None:
    t = await new_teacher()
    t.repo._peer_worked = worked(N)  # type: ignore[attr-defined]
    await due_and_offered(t, flags)
    assert line(N) not in alltext(await t.tap(followup.BTN_WORKED))


@pytest.mark.asyncio
async def test_check_in_tip_screen_shows_it_before_the_practice_button(lang: str) -> None:
    t = await new_teacher()
    t.repo._peer_worked = worked(N + 1)  # type: ignore[attr-defined]
    await check_in(t, STRUGGLE)
    last = t.transcript[-1][1]
    joined = "\n".join(last)
    assert line(N + 1) in joined
    assert last.index(next(x for x in last if line(N + 1) in x)) < len(last) - 1
    assert checkin_flow.BTN_PRACTICE in ids(await _redo(t))


async def _redo(t: Teacher) -> list:  # type: ignore[type-arg]
    return await t.service._with_peer_line(
        t.teacher_id, STRUGGLE, checkin_flow.result_messages(await t.ctx(), _struggle())
    )


def _struggle():  # type: ignore[no-untyped-def]
    from backend.app.class_profile.library import load_library

    s = load_library().get(STRUGGLE)
    assert s is not None
    return s


@pytest.mark.asyncio
async def test_check_in_tip_without_data_is_unchanged(lang: str) -> None:
    t = await new_teacher()
    await check_in(t, STRUGGLE)
    assert "शिक्षकों ने बताया" not in "\n".join(t.transcript[-1][1])
    assert "teachers said" not in "\n".join(t.transcript[-1][1])


# ── flag off ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_flag_off_adds_nothing(monkeypatch: pytest.MonkeyPatch, flags: Clock) -> None:
    t = await new_teacher()
    t.repo._peer_worked = worked(N + 3)  # type: ignore[attr-defined]
    await due_and_offered(t, flags)
    monkeypatch.setattr(settings, "PEER_WORKED_ENABLED", False)
    out = await t.tap(followup.BTN_STUCK)
    assert line(N + 3) not in alltext(out)
    assert settings.model_fields["PEER_WORKED_ENABLED"].default is False


@pytest.mark.asyncio
async def test_demo_mode_turns_it_on(monkeypatch: pytest.MonkeyPatch, flags: Clock) -> None:
    monkeypatch.setattr(settings, "PEER_WORKED_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    t = await new_teacher()
    t.repo._peer_worked = worked(N, demo=True)  # type: ignore[attr-defined]
    row = await t.repo.get_or_create_teacher(t.teacher_id)
    row.is_demo = True
    await due_and_offered(t, flags)
    assert line(N) in alltext(await t.tap(followup.BTN_STUCK))


def test_catalog_twins_and_no_dashes() -> None:
    for code in ("hi", "en"):
        text = get_message("pw_line", lang=code, n=12, move="X")
        assert "12" in text and "'X'" in text
        assert not any(d in text for d in DASHES)
    assert date(2026, 10, 30) == FRIDAY
