"""The level sorter ("Group my class by level") through the real SessionService (mocks only).

Both subjects, the edge cases (all children at one level, empty levels, four levels merged into
three groups, nothing chosen), flag off and on, Hindi and English, address form she and he, the
demo2 and demo3 profiles, the paused scene, and the content: every citation resolves to a stored
chunk. No LLM is involved anywhere in the flow.
"""

# ruff: noqa: F811  (the page tests reuse the teacher_pwa_app fixtures by name)
from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_class_checkin import PROFILES, Teacher, alltext, ids  # noqa: F401
from test_teacher_pwa import mock_teacher, mock_teacher_id, teacher_pwa_app  # noqa: F401

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.class_profile import level_sorter as ls
from backend.app.class_profile.library import _chunk_index
from backend.app.config import settings
from backend.app.core.messages import (
    DEFAULT_LANG,
    FEMININE_MARKERS,
    get_catalog,
    get_message,
    reset_ui_lang,
    set_ui_lang,
)
from backend.app.core.types import OutboundMessage
from backend.app.db.models import Teacher as TeacherRow
from backend.app.sessions.state_machine import SessionStateEnum

CONTENT = ls.load_content()
SUBJECTS = list(CONTENT.subjects)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
BUCKETS = list(settings.LEVEL_BUCKET_COUNTS)


@pytest.fixture(autouse=True)
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", True)
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


def _count_button(bucket: str) -> str:
    return f"{ls.COUNT_PREFIX}{bucket}"


async def run_sorter(t: Teacher, subject: str, buckets: list[str]) -> list[OutboundMessage]:
    """Start, pick the subject, tap one range per level; returns what the last tap produced."""
    out = await t.tap(ls.BTN_START)
    assert ids(out) == [f"{ls.SUBJECT_PREFIX}{s}" for s in SUBJECTS]
    out = await t.tap(f"{ls.SUBJECT_PREFIX}{subject}")
    for bucket in buckets:
        assert ids(out) == [_count_button(b) for b in BUCKETS]
        out = await t.tap(_count_button(bucket))
    return out


# ── content ─────────────────────────────────────────────────────────────────────────────────
def test_content_validates_and_every_chunk_is_stored() -> None:
    assert ls.validate_content() == []
    index = _chunk_index()
    for level in CONTENT.levels.values():
        assert level.chunk_ids
        assert all(c in index for c in level.chunk_ids)
        assert DEVANAGARI.search(level.activity_hi)
        assert not DEVANAGARI.search(level.activity_en)


def test_level_names_and_activities_match_the_two_subjects() -> None:
    assert CONTENT.subjects["reading"].levels == ["letter", "word", "paragraph", "story"]
    assert CONTENT.subjects["maths"].levels == [
        "number_recognition",
        "one_digit",
        "two_digit",
        "subtraction",
    ]


def test_multigrade_line_only_where_a_stored_chunk_supports_it() -> None:
    index = _chunk_index()
    reading = CONTENT.subjects["reading"].multigrade
    assert reading is not None and all(c in index for c in reading.chunk_ids)
    assert CONTENT.subjects["maths"].multigrade is None  # no stored maths chunk says it


def test_validation_flags_an_unknown_chunk(tmp_path: pytest.TempPathFactory) -> None:
    bad = CONTENT.model_copy(deep=True)
    bad.levels["letter"].chunk_ids = ["nope:p001:001"]
    assert any("nope:p001:001" in e for e in ls.validate_content(bad))


@pytest.mark.parametrize("code", [DEFAULT_LANG, "en"])
def test_catalog_has_every_sorter_key(code: str) -> None:
    catalog = get_catalog(lang=code)
    keys = {ls.BTN_START, ls.BTN_HANDBOOK, ls.BTN_RESUME, "ui_level_entry", "lvl_command_words"}
    keys |= {f"{ls.SUBJECT_PREFIX}{s}" for s in SUBJECTS} | {f"lvl_subject_{s}" for s in SUBJECTS}
    keys |= {f"lvl_label_{lv}" for s in CONTENT.subjects.values() for lv in s.levels}
    keys |= {_count_button(b) for b in BUCKETS} | {f"lvl_count_label_{b}" for b in BUCKETS}
    keys |= {
        "lvl_subject_ask",
        "lvl_count_ask",
        "lvl_pick_button",
        "lvl_empty",
        "lvl_head_one",
        "lvl_head_many",
        "lvl_first",
        "lvl_merged_note",
        "lvl_group",
        "lvl_group_missing",
        "lvl_multigrade",
        "lvl_after",
        "lvl_scene_waiting",
        "lvl_already",
    }
    assert not sorted(k for k in keys if not catalog.has(k)), code
    for key in keys:
        if key.startswith("btn_lvl_"):
            assert 0 < len(get_message(key, lang=code)) <= settings.WHATSAPP_BUTTON_TITLE_MAX


def test_no_feminine_only_wording_in_the_sorter_texts() -> None:
    for key in get_catalog(lang=DEFAULT_LANG).keys():
        if key.startswith(("lvl_", "btn_lvl_", "ui_level")):
            text = get_message(key, lang=DEFAULT_LANG, **_dummy_args(key))
            assert not any(re.search(m, text) for m in FEMININE_MARKERS), key


def _dummy_args(key: str) -> dict[str, object]:
    spec = get_catalog(lang=DEFAULT_LANG).get_spec(key).get("text", "")
    return dict.fromkeys(re.findall(r"{(\w+)}", str(spec)), "x")


# ── grouping rule ───────────────────────────────────────────────────────────────────────────
LEVELS = ["a", "b", "c", "d"]


def test_all_children_at_one_level_make_one_group() -> None:
    groups = ls.plan_groups(LEVELS, {"a": "0", "b": "11_20", "c": "0", "d": "0"})
    assert groups == [ls.Group(("b",))]


def test_empty_levels_are_skipped_and_order_is_lowest_first() -> None:
    groups = ls.plan_groups(LEVELS, {"a": "6_10", "b": "0", "c": "1_5", "d": "0"})
    assert groups == [ls.Group(("a",)), ls.Group(("c",))]


def test_nothing_chosen_makes_no_group() -> None:
    assert ls.plan_groups(LEVELS, dict.fromkeys(LEVELS, "0")) == []
    assert ls.plan_groups(LEVELS, {}) == []


def test_four_levels_merge_the_two_neighbours_with_fewest_children() -> None:
    counts = {"a": "11_20", "b": "1_5", "c": "1_5", "d": "11_20"}
    assert ls.plan_groups(LEVELS, counts) == [
        ls.Group(("a",)),
        ls.Group(("b", "c")),
        ls.Group(("d",)),
    ]


def test_merge_tie_goes_to_the_lower_pair() -> None:
    counts = dict.fromkeys(LEVELS, "6_10")
    assert ls.plan_groups(LEVELS, counts) == [
        ls.Group(("a", "b")),
        ls.Group(("c",)),
        ls.Group(("d",)),
    ]


def test_never_more_than_the_configured_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LEVEL_MAX_GROUPS", 2)
    counts = dict.fromkeys(LEVELS, "6_10")
    assert len(ls.plan_groups(LEVELS, counts)) == 2


# ── the flow, both subjects ─────────────────────────────────────────────────────────────────
def _group_prefix() -> str:
    return get_message("lvl_group", n=0, levels="", minutes=0, activity="", sources="").split("0")[
        0
    ]


def _all_cited(out: list[OutboundMessage]) -> None:
    index = _chunk_index()
    for m in out:
        for c in m.citations:
            assert c.chunk_id in index
            assert c.line_hi and c.line_hi in m.text_hi


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["f", "m"])
@pytest.mark.parametrize("profile", ["demo2", "demo3"])
@pytest.mark.parametrize("subject", SUBJECTS)
async def test_three_groups_with_one_activity_each(
    lang: str, form: str, profile: str, subject: str
) -> None:
    t = await Teacher(profile, form).setup()
    levels = CONTENT.subjects[subject].levels
    out = await run_sorter(t, subject, ["6_10", "0", "11_20", "1_5"])
    text = alltext(out)
    assert get_message("lvl_head_many", n=3, subject=ls.subject_label(subject)) in text
    first_level = CONTENT.levels[levels[0]]
    last_level = CONTENT.levels[levels[3]]
    assert (first_level.activity_en if lang == "en" else first_level.activity_hi) in text
    assert (last_level.activity_en if lang == "en" else last_level.activity_hi) in text
    assert str(settings.LEVEL_ACTIVITY_MINUTES) in text
    assert get_message("lvl_first", sources="").strip().split("\n")[0] in text
    _all_cited(out)
    # the plan needs sources: every group message has at least one citation
    group_msgs = [m for m in out if m.text_hi.startswith(_group_prefix())]
    assert len(group_msgs) == 3 and all(m.citations for m in group_msgs)
    assert [m.text_hi.split(":")[0] for m in group_msgs] == [
        f"{_group_prefix()}{n}" for n in (1, 2, 3)
    ]
    if form == "m":
        assert not any(re.search(m, text) for m in FEMININE_MARKERS)
    # offers only the handbook afterwards (a drill-down), and the stage is the finished one
    assert ids(out[-1:]) == [ls.BTN_HANDBOOK]
    ctx = await t.ctx()
    assert ctx.level_stage == ls.STAGE_RESULT and ctx.level_counts == {}


@pytest.mark.asyncio
async def test_reading_adds_the_multigrade_line_with_its_citation(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    out = await run_sorter(t, "reading", ["6_10", "11_20", "0", "0"])
    mg = CONTENT.subjects["reading"].multigrade
    assert mg is not None
    line = mg.text_en if lang == "en" else mg.text_hi
    assert any(line in m.text_hi and m.citations for m in out)
    maths_t = await Teacher("demo3", "f").setup()
    maths = await run_sorter(maths_t, "maths", ["6_10", "11_20", "0", "0"])
    assert not any(mg.text_hi in m.text_hi or mg.text_en in m.text_hi for m in maths)
    assert not any(c.chunk_id in mg.chunk_ids for m in maths for c in m.citations)


@pytest.mark.asyncio
async def test_all_children_at_one_level_gives_one_group_and_no_first_group_line(
    lang: str,
) -> None:
    t = await Teacher("demo2", "f").setup()
    out = await run_sorter(t, "maths", ["0", "0", "20p", "0"])
    text = alltext(out)
    assert get_message("lvl_head_one", subject=ls.subject_label("maths")) in text
    assert get_message("lvl_first", sources="").strip().split("\n")[0] not in text
    two = CONTENT.levels["two_digit"]
    assert (two.activity_en if lang == "en" else two.activity_hi) in text
    _all_cited(out)


@pytest.mark.asyncio
async def test_four_levels_say_that_two_were_merged(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    out = await run_sorter(t, "reading", ["1_5", "1_5", "6_10", "11_20"])
    text = alltext(out)
    assert get_message("lvl_head_many", n=3, subject=ls.subject_label("reading")) in text
    assert get_message("lvl_merged_note") in text
    assert " + " in text  # the merged group names both levels


@pytest.mark.asyncio
async def test_nothing_chosen_says_so_and_offers_a_fresh_start(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    out = await run_sorter(t, "reading", ["0", "0", "0", "0"])
    assert get_message("lvl_empty") in alltext(out)
    assert ids(out) == [ls.BTN_START]
    ctx = await t.ctx()
    assert ctx.level_stage == ls.STAGE_NONE
    again = await t.tap(ls.BTN_START)  # the offered button works
    assert ids(again) == [f"{ls.SUBJECT_PREFIX}{s}" for s in SUBJECTS]


@pytest.mark.asyncio
async def test_a_level_without_stored_content_is_said_honestly(
    lang: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = CONTENT.model_copy(deep=True)
    broken.levels["letter"].chunk_ids = ["not_stored:p001:001"]
    monkeypatch.setattr(ls, "load_content", lambda path=None: broken)
    t = await Teacher("demo2", "f").setup()
    out = await run_sorter(t, "reading", ["6_10", "0", "0", "0"])
    text = alltext(out)
    assert get_message("lvl_group_missing", n=1, levels="x").split(chr(10))[1] in text
    missing = [
        m
        for m in out
        if get_message("lvl_group_missing", n=1, levels="x").split(chr(10))[1] in m.text_hi
    ]
    assert len(missing) == 1 and not missing[0].citations
    assert not any(c.chunk_id.startswith("not_stored") for m in out for c in m.citations)


@pytest.mark.asyncio
async def test_nothing_about_a_child_is_asked_or_stored(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await run_sorter(t, "maths", ["1_5", "6_10", "6_10", "1_5"])
    assert t.stored() == []  # no check-in or any other record
    assert not t.repo._class_checkins
    ctx = await t.ctx()
    assert ctx.level_counts == {}  # the tapped ranges are cleared once the plan is shown
    asked = " ".join(line for _, lines in t.transcript for line in lines)
    assert (
        get_message("lvl_count_ask", subject="x", level="y", step=1, total=4)
        .split("x")[1]
        .split("y")[1]
        in asked
    )  # the screen tells her no name is needed


# ── reach: within two taps from demo2 and demo3 ──────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["demo2", "demo3"])
async def test_reachable_within_two_taps_for_the_demo_accounts(lang: str, profile: str) -> None:
    t = await Teacher(profile, "f").setup()
    first = await t.tap(ls.BTN_START)  # tap 1: the chip
    assert ids(first) == [f"{ls.SUBJECT_PREFIX}{s}" for s in SUBJECTS]
    second = await t.tap(f"{ls.SUBJECT_PREFIX}reading")  # tap 2: a subject, first count screen
    assert ids(second) == [_count_button(b) for b in BUCKETS]
    assert len(ids(second)) <= settings.CHECKIN_MAX_BUTTONS


@pytest.mark.asyncio
async def test_typed_command_words_start_it_and_typing_mid_flow_reshows_the_screen(
    lang: str,
) -> None:
    t = await Teacher("demo2", "f").setup()
    out = await t.say("group my class")
    assert ids(out) == [f"{ls.SUBJECT_PREFIX}{s}" for s in SUBJECTS]
    again = await t.say("रवि")  # a name typed instead of tapping: not read, screen shown again
    assert get_message("lvl_pick_button") in alltext(again)
    assert ids(again) == [f"{ls.SUBJECT_PREFIX}{s}" for s in SUBJECTS]


@pytest.mark.asyncio
async def test_an_old_button_after_the_plan_is_ignored_politely(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    await run_sorter(t, "maths", ["6_10", "0", "0", "0"])
    out = await t.tap(_count_button("1_5"))
    assert get_message("lvl_already") in alltext(out)
    out = await t.tap(f"{ls.SUBJECT_PREFIX}maths")
    assert get_message("lvl_already") in alltext(out)


@pytest.mark.asyncio
async def test_handbook_button_goes_to_the_ask_prompt(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    await run_sorter(t, "reading", ["6_10", "6_10", "0", "0"])
    out = await t.tap(ls.BTN_HANDBOOK)
    assert out[0].text_hi == get_message("ask_prompt", "f")
    assert (await t.ctx()).current_state == SessionStateEnum.ASK


@pytest.mark.asyncio
async def test_starting_the_sorter_drops_an_open_check_in_and_back(lang: str) -> None:
    from backend.app.class_profile import checkin_flow

    t = await Teacher("demo2", "f").setup()
    await t.tap(checkin_flow.BTN_START)
    assert (await t.ctx()).checkin_stage == checkin_flow.STAGE_MODULE
    await t.tap(ls.BTN_START)
    ctx = await t.ctx()
    assert ctx.checkin_stage == "" and ctx.level_stage == ls.STAGE_SUBJECT
    await t.tap(checkin_flow.BTN_START)
    ctx = await t.ctx()
    assert ctx.level_stage == "" and ctx.checkin_stage == checkin_flow.STAGE_MODULE


# ── a running scene is paused, never touched ─────────────────────────────────────────────────
async def _scene_fields(t: Teacher) -> tuple[object, ...]:
    c = await t.ctx()
    return (
        c.current_state,
        c.current_move_id,
        c.rehearse_mode,
        c.rehearse_child,
        c.rehearsal_turns_count,
        c.retries_count,
        c.diagnosis,
        c.resume_scene_id,
    )


@pytest.mark.asyncio
async def test_inside_a_scene_it_pauses_and_resumes_without_touching_the_scene(
    lang: str,
) -> None:
    t = await Teacher("demo2", "f").setup()
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE
    ctx.rehearse_mode = "one_on_one"
    ctx.rehearse_child = "ravi"
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    before = await _scene_fields(t)
    out = await run_sorter(t, "maths", ["6_10", "1_5", "0", "0"])
    assert ids(out[-1:]) == [ls.BTN_RESUME, ls.BTN_HANDBOOK]
    assert get_message("lvl_scene_waiting") in alltext(out)
    assert await _scene_fields(t) == before
    back = await t.tap(ls.BTN_RESUME)
    assert await _scene_fields(t) == before
    assert back and back[0].kind == "text"
    ctx = await t.ctx()
    assert ctx.level_stage == ""


@pytest.mark.asyncio
async def test_typing_inside_a_scene_drops_the_unfinished_sorter(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    await t.tap(ls.BTN_START)
    await t.say("तुमने कैसे किया?")
    assert (await t.ctx()).level_stage == ""
    assert (await t.ctx()).current_state == SessionStateEnum.REHEARSE


@pytest.mark.asyncio
async def test_not_offered_while_choosing_the_child_for_a_scene(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE_INTRO
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    await t.tap(ls.BTN_START)
    assert (await t.ctx()).level_stage == ""


# ── flag off ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_flag_off_nothing_starts(lang: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", False)
    t = await Teacher("demo2", "f").setup()
    await t.tap(ls.BTN_START)
    assert (await t.ctx()).level_stage == ""
    await t.say("group my class")
    assert (await t.ctx()).level_stage == ""


def test_flag_default_is_off_and_demo_mode_turns_it_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.config import v2_enabled

    assert settings.model_fields["LEVEL_SORTER_ENABLED"].default is False
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert not v2_enabled(settings.LEVEL_SORTER_ENABLED)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert v2_enabled(settings.LEVEL_SORTER_ENABLED)


# ── channel caps ────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_count_screen_is_five_buttons_on_web_and_a_list_on_whatsapp(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    await t.tap(ls.BTN_START)
    out = await t.tap(f"{ls.SUBJECT_PREFIX}reading")
    msg = out[0]
    assert len(msg.buttons) == 5
    plan = plan_buttons(msg.buttons, has_audio=False)
    assert not plan.reply_buttons and len(plan.list_rows) == 5
    assert all(len(title) <= settings.WHATSAPP_BUTTON_TITLE_MAX for _, title, _ in plan.list_rows)


# ── hint and page ───────────────────────────────────────────────────────────────────────────
def test_next_action_hint_while_the_sorter_is_open(lang: str) -> None:
    from backend.app.sessions.state_machine import OnboardingStateEnum
    from backend.app.web.next_action import next_action

    for stage in ("subject", "count"):
        hint = next_action(
            onboarding=OnboardingStateEnum.READY.value,
            state=SessionStateEnum.DONE.value,
            context={"level_stage": stage},
            retries=0,
            address_form="f",
            started=True,
            scene=None,
        )
        assert hint is not None and hint["text"] == get_message("hint_checkin")
    done = next_action(
        onboarding=OnboardingStateEnum.READY.value,
        state=SessionStateEnum.DONE.value,
        context={"level_stage": "result"},
        retries=0,
        address_form="f",
        started=True,
        scene=None,
    )
    assert done is not None and done["key"] == "hint_done"


async def _page(app: FastAPI) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return (await client.get("/teacher")).text


@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
async def test_page_shows_the_chip_next_to_the_check_in_chip(
    teacher_pwa_app: FastAPI, mock_teacher: TeacherRow, address_form: str
) -> None:
    mock_teacher.onboarding_state = "READY"
    mock_teacher.address_form = address_form
    html = await _page(teacher_pwa_app)
    assert 'data-btn-id="btn_lvl_start"' in html and 'data-btn-id="btn_chk_start"' in html
    assert get_message("ui_level_entry", lang="hi") in html
    assert html.count('id="checkin-entry"') == 1


@pytest.mark.asyncio
async def test_page_chip_without_the_check_in_flag(
    teacher_pwa_app: FastAPI, mock_teacher: TeacherRow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", False)
    mock_teacher.onboarding_state = "READY"
    html = await _page(teacher_pwa_app)
    assert 'data-btn-id="btn_lvl_start"' in html and 'data-btn-id="btn_chk_start"' not in html
    assert html.count('id="checkin-entry"') == 1


@pytest.mark.asyncio
async def test_page_has_no_chip_when_off_or_not_onboarded(
    teacher_pwa_app: FastAPI, mock_teacher: TeacherRow, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_teacher.onboarding_state = "READY"
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", False)
    assert "btn_lvl_start" not in await _page(teacher_pwa_app)
    monkeypatch.setattr(settings, "LEVEL_SORTER_ENABLED", True)
    mock_teacher.onboarding_state = "NEW"
    assert "btn_lvl_start" not in await _page(teacher_pwa_app)


@pytest.mark.asyncio
async def test_page_chip_label_is_english_in_the_english_ui(
    teacher_pwa_app: FastAPI, mock_teacher: TeacherRow
) -> None:
    from backend.app.web.ui_lang import LANG_COOKIE_NAME, UiLangMiddleware

    mock_teacher.onboarding_state = "READY"
    teacher_pwa_app.add_middleware(UiLangMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=teacher_pwa_app), base_url="http://test"
    ) as c:
        html = (await c.get("/teacher", cookies={LANG_COOKIE_NAME: "en"})).text
    assert get_message("ui_level_entry", lang="en") in html
