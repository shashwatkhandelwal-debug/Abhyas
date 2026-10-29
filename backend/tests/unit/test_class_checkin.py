"""The "After class: how did it go?" check-in through the real SessionService (mocks only).

Every path, flag off and on, Hindi and English, address form she and he, the demo2 and demo3
profiles, a mapped-only struggle (a tip but no practice move), the rehearsal launch and idempotence.
No LLM is involved anywhere in the flow.
"""

# ruff: noqa: F811  (the page tests reuse the teacher_pwa_app fixtures by name)
from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_state_machine import FakeSessionRepository
from test_teacher_pwa import mock_teacher, mock_teacher_id, teacher_pwa_app  # noqa: F401

from backend.app.class_profile import checkin_flow
from backend.app.class_profile.library import load_library
from backend.app.config import settings, v2_enabled
from backend.app.core.messages import (
    FEMININE_MARKERS,
    get_message,
    reset_ui_lang,
    set_ui_lang,
)
from backend.app.core.types import InboundMessage, OutboundMessage
from backend.app.db.models import Teacher as TeacherRow
from backend.app.sessions.path import MovePathEntry
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.app.sessions.titles import move_title

LIB = load_library()
MODULES = checkin_flow.modules(LIB)
MAPPED = [s for s in LIB.struggles if s.move_id]
MAPPED_ONLY = [s for s in LIB.struggles if not s.move_id]
DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Profiles of the seeded demo teachers (db/seed.py): where each one is when scene-free
PROFILES: dict[str, dict[str, Any]] = {
    "demo2": {
        "name": "डेमो शिक्षिका 2 (अनीता)",
        "move": "NUM_SUB_REGROUP_BUNDLES",
        "state": SessionStateEnum.DONE,
        "struggles": [],
        "path": [],
    },
    "demo3": {
        "name": "डेमो शिक्षिका 3 (रेखा)",
        "move": "LIT_MATRA_BLENDING",
        "state": SessionStateEnum.LEARN,
        "struggles": ["LIT_MATRA_DROP", "NUM_ADD_CARRY"],
        "path": ["LIT_MATRA_BLENDING", "NUM_ADD_CARRY_BUNDLES"],
    },
}


@pytest.fixture(autouse=True)
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


def _inbound(teacher_id: UUID, text: str | None, button: str | None) -> InboundMessage:
    return InboundMessage(
        channel="web",
        channel_msg_id=f"m-{uuid4().hex[:8]}",
        teacher_id=teacher_id,
        kind="button" if button else "text",
        text=text,
        button_id=button,
        received_at=datetime.now(UTC),
    )


class Teacher:
    """One teacher on the real SessionService with the in-memory repository."""

    def __init__(self, profile: str, address_form: str) -> None:
        self.repo = FakeSessionRepository()
        self.service = SessionService(repository=self.repo)
        self.teacher_id = uuid4()
        self.profile = PROFILES[profile]
        self.address_form = address_form
        self.transcript: list[tuple[str, list[str]]] = []

    async def setup(self) -> Teacher:
        p = self.profile
        ctx = await self.service.get_or_create_context(self.teacher_id)
        ctx.onboarding_state = OnboardingStateEnum.READY
        ctx.current_move_id = p["move"]
        ctx.current_state = p["state"]
        ctx.name = p["name"]
        ctx.address_form = self.address_form
        ctx.class_struggles = list(p["struggles"])
        await self.service._sync_context_to_db(ctx, self.teacher_id)
        if p["path"]:
            await self.repo.record_move_path(
                self.teacher_id,
                [MovePathEntry(i + 1, m, "induction") for i, m in enumerate(p["path"])],
            )
        return self

    async def tap(self, button: str) -> list[OutboundMessage]:
        out = await self.service.handle_inbound(_inbound(self.teacher_id, None, button))
        self.transcript.append((button, _render(out)))
        return out

    async def say(self, text: str) -> list[OutboundMessage]:
        out = await self.service.handle_inbound(_inbound(self.teacher_id, text, None))
        self.transcript.append((text, _render(out)))
        return out

    async def ctx(self) -> Any:
        return await self.service.get_or_create_context(self.teacher_id)

    def stored(self) -> list[Any]:
        return [c for c in self.repo._class_checkins if c.teacher_id == self.teacher_id]


def _render(out: list[OutboundMessage]) -> list[str]:
    lines: list[str] = []
    for m in out:
        lines.append(m.text_hi or "")
        lines.extend(f"[{b.title_hi}]" for b in m.buttons)
    return lines


def ids(out: list[OutboundMessage]) -> list[str]:
    return [b.id for m in out for b in m.buttons]


def alltext(out: list[OutboundMessage]) -> str:
    return "\n".join(
        (m.text_hi or "") + "\n" + "\n".join(b.title_hi for b in m.buttons) for m in out
    )


def module_button(module_id: str) -> str:
    return f"{checkin_flow.MODULE_PREFIX}{module_id}"


def struggle_button(struggle_id: str) -> str:
    return f"{checkin_flow.STRUGGLE_PREFIX}{struggle_id}"


async def open_module(t: Teacher, module_id: str) -> list[OutboundMessage]:
    """Entry, then the module (paging through "more" when the module is on a later page)."""
    out = await t.tap(checkin_flow.BTN_START)
    for _ in range(4):
        if module_button(module_id) in ids(out):
            return await t.tap(module_button(module_id))
        out = await t.tap(checkin_flow.BTN_MORE)
    raise AssertionError(f"module {module_id} never offered")


async def open_struggle_list(t: Teacher, module_id: str, outcome: str) -> list[OutboundMessage]:
    await open_module(t, module_id)
    return await t.tap(outcome)


# ── the closed lists come from existing content ────────────────────────────────────────────
def test_modules_are_derived_from_the_struggle_library() -> None:
    move_modules = [m.id for m in MODULES if not m.id.startswith("OTHER_")]
    assert move_modules == list(dict.fromkeys(s.move_id for s in LIB.struggles if s.move_id))
    assert {"NUM_SUB_REGROUP_BUNDLES", "NUM_ADD_CARRY_BUNDLES", "NUM_PLACE_VALUE_BUNDLES"} <= set(
        move_modules
    )
    assert "LIT_MATRA_BLENDING" in move_modules
    # every struggle is in exactly one module
    placed = [sid for m in MODULES for sid in m.struggle_ids]
    assert sorted(placed) == sorted(LIB.ids())


def test_every_label_exists_in_both_catalogs_and_fits_a_button() -> None:
    keys = [module_button(m.id) for m in MODULES] + [struggle_button(s.id) for s in LIB.struggles]
    keys += [*checkin_flow.OUTCOME_BUTTONS, checkin_flow.BTN_START, checkin_flow.BTN_MORE]
    keys += [checkin_flow.BTN_PRACTICE, checkin_flow.BTN_HANDBOOK]
    for code in ("hi", "en"):
        for key in keys:
            assert 0 < len(get_message(key, lang=code)) <= 20, (key, code)
    assert get_message("ui_checkin_entry", lang="hi") == "कक्षा के बाद: कैसा रहा?"
    assert get_message("ui_checkin_entry", lang="en") == "After class: how did it go?"


def test_no_catch_up_option_because_the_handbook_has_no_catch_up_chunks() -> None:
    assert not any("absent" in s.id.lower() or "CATCH" in s.id for s in LIB.struggles)
    assert not any("ABSENT" in m.id for m in MODULES)


# ── flag ───────────────────────────────────────────────────────────────────────────────────
def test_v2_enabled_is_on_in_demo_mode_and_off_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert v2_enabled(False) and v2_enabled(True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert not v2_enabled(False) and v2_enabled(True)
    assert settings.model_fields["CLASS_CHECKIN_ENABLED"].default is False


@pytest.mark.asyncio
async def test_flag_off_the_check_in_does_not_start_and_adds_no_button(
    lang: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    t = await Teacher("demo3", "f").setup()
    out = await t.tap(checkin_flow.BTN_START)
    assert (await t.ctx()).checkin_stage == ""
    assert module_button("NUM_SUB_REGROUP_BUNDLES") not in ids(out)
    assert checkin_flow.BTN_START not in [b.id for b in SessionService._checkin_entry_buttons()]
    assert t.stored() == []


@pytest.mark.asyncio
async def test_demo_mode_turns_it_on_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    t = await Teacher("demo3", "f").setup()
    out = await t.tap(checkin_flow.BTN_START)
    assert module_button("LIT_MATRA_BLENDING") in ids(out)


# ── every path ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
@pytest.mark.parametrize("profile", ["demo2", "demo3"])
async def test_module_screen_buttons_and_two_taps_to_the_outcome(
    lang: str, profile: str, address_form: str
) -> None:
    t = await Teacher(profile, address_form).setup()
    out = await t.tap(checkin_flow.BTN_START)  # tap 1: the entry
    first = ids(out)
    assert len(first) <= settings.CHECKIN_MAX_BUTTONS
    assert [module_button(m.id) for m in MODULES if not m.id.startswith("OTHER_")] == first[:4]
    assert first[-1] == checkin_flow.BTN_MORE
    out = await t.tap(module_button("NUM_SUB_REGROUP_BUNDLES"))  # tap 2: a module
    assert ids(out) == list(checkin_flow.OUTCOME_BUTTONS)
    assert t.stored() == []  # nothing is stored before the outcome is complete


@pytest.mark.asyncio
async def test_more_pages_to_the_other_topics_and_wraps(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await t.tap(checkin_flow.BTN_START)
    out = await t.tap(checkin_flow.BTN_MORE)
    assert ids(out)[:2] == [module_button("OTHER_numeracy"), module_button("OTHER_literacy")]
    assert len(ids(out)) <= settings.CHECKIN_MAX_BUTTONS
    out = await t.tap(checkin_flow.BTN_MORE)
    assert module_button("NUM_SUB_REGROUP_BUNDLES") in ids(out)


@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
@pytest.mark.parametrize("profile", ["demo2", "demo3"])
async def test_went_well_acknowledges_stores_and_offers_the_next_move(
    lang: str, profile: str, address_form: str
) -> None:
    t = await Teacher(profile, address_form).setup()
    module = "NUM_ADD_CARRY_BUNDLES"
    await open_module(t, module)
    out = await t.tap("btn_chk_well")
    text = alltext(out)
    assert len(out) == 1
    assert (await t.ctx()).checkin_stage == ""
    [row] = t.stored()
    assert (row.module_id, row.outcome, row.struggle_ids) == (module, "well", [])
    assert "!" not in text and "शाबाश" not in text and "great" not in text.lower()
    if profile == "demo2":  # DONE state and no later move on the path: no next-move offer
        assert "btn_next_move" not in ids(out)
        assert get_message("chk_well_next", next_move_title="").split("{")[0] not in text


@pytest.mark.asyncio
async def test_went_well_offers_next_move_button_when_done_and_a_later_move_exists(
    lang: str,
) -> None:
    t = await Teacher("demo3", "f").setup()
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.DONE
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    await open_module(t, "LIT_MATRA_BLENDING")
    out = await t.tap("btn_chk_well")
    assert ids(out) == ["btn_next_move"]
    assert "NUM_ADD_CARRY" not in alltext(out)  # titles, never raw ids
    assert move_title("NUM_ADD_CARRY_BUNDLES") in alltext(out)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["btn_chk_some", "btn_chk_most"])
@pytest.mark.parametrize("struggle", LIB.struggles, ids=lambda s: s.id)
async def test_struggle_path_tip_citations_and_the_next_buttons(
    lang: str, outcome: str, struggle: Any
) -> None:
    t = await Teacher("demo2", "f").setup()
    module = next(m.id for m in MODULES if struggle.id in m.struggle_ids)
    listed = await open_struggle_list(t, module, outcome)
    assert struggle_button(struggle.id) in ids(listed)
    assert len(ids(listed)) <= settings.CHECKIN_MAX_BUTTONS
    out = await t.tap(struggle_button(struggle.id))
    tip, offer = out
    expected_tip = struggle.tip_en if lang == "en" else struggle.tip_hi
    assert expected_tip in (tip.text_hi or "")
    assert len(tip.citations) == len(struggle.chunk_ids) >= 1
    for cite in tip.citations:  # the existing citation line is in the text, with a chip
        assert cite.line_hi in (tip.text_hi or "")
        assert cite.chunk_id in struggle.chunk_ids
    if struggle.move_id:
        assert ids([offer]) == [checkin_flow.BTN_PRACTICE, checkin_flow.BTN_HANDBOOK]
        assert move_title(struggle.move_id) in offer.text_hi
    else:
        assert ids([offer]) == [checkin_flow.BTN_HANDBOOK]
        assert offer.text_hi == get_message("chk_practice_none")
    [row] = t.stored()
    assert (row.module_id, row.outcome, row.struggle_ids) == (
        module,
        outcome.removeprefix("btn_chk_"),
        [struggle.id],
    )
    # no "try this week" line: the content supplies none
    assert "इस हफ्ते आज़माएँ" not in alltext(out)


def test_the_library_has_both_kinds_of_struggle() -> None:
    """Seven of the fourteen have a practice move (the run brief said six), seven have a tip only."""
    assert (len(MAPPED), len(MAPPED_ONLY), len(LIB.struggles)) == (7, 7, 14)


@pytest.mark.asyncio
async def test_the_tip_is_the_stored_paraphrase_with_no_english_passage_in_hindi() -> None:
    t = await Teacher("demo3", "f").setup()
    await open_struggle_list(t, "LIT_MATRA_BLENDING", "btn_chk_some")
    tip = (await t.tap(struggle_button("LIT_MATRA_DROP")))[0]
    letters = re.findall(r"[A-Za-z]+", re.sub(r"\{[^}]*\}", "", tip.text_hi or ""))
    assert not [w for w in letters if len(w) > 2]  # only chunk ids may be Latin; none are shown


# ── mapped-only struggle ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mapped_only_struggle_is_honest_and_offers_the_handbook(lang: str) -> None:
    s = MAPPED_ONLY[0]
    t = await Teacher("demo3", "m").setup()
    module = next(m.id for m in MODULES if s.id in m.struggle_ids)
    assert module.startswith("OTHER_")
    await open_struggle_list(t, module, "btn_chk_most")
    tip, offer = await t.tap(struggle_button(s.id))
    assert tip.citations
    assert offer.text_hi == get_message("chk_practice_none")
    assert checkin_flow.BTN_PRACTICE not in ids([offer])
    # the handbook button hands over to the existing ask flow
    out = await t.tap(checkin_flow.BTN_HANDBOOK)
    assert (await t.ctx()).checkin_stage == ""
    assert alltext(out).strip() == get_message("ask_prompt")
    assert (await t.ctx()).current_state == SessionStateEnum.ASK


# ── rehearsal launch ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
async def test_practice_button_opens_the_rehearsal_for_the_struggles_move(
    lang: str, address_form: str
) -> None:
    s = next(x for x in LIB.struggles if x.id == "NUM_SUB_REGROUP")
    t = await Teacher("demo2", address_form).setup()
    await open_struggle_list(t, "NUM_SUB_REGROUP_BUNDLES", "btn_chk_some")
    await t.tap(struggle_button(s.id))
    out = await t.tap(checkin_flow.BTN_PRACTICE)
    ctx = await t.ctx()
    assert ctx.current_move_id == s.move_id
    assert ctx.current_state == SessionStateEnum.REHEARSE_INTRO
    assert ctx.rehearse_stage == "choose_mode"
    assert ids(out) == ["btn_rehearse_one", "btn_rehearse_group"]
    assert ctx.checkin_stage == "" and ctx.checkin_jump_move == s.move_id
    # the practice then runs as it always does: pick one child and the scene opens on the move
    out = await t.tap("btn_rehearse_one")
    assert "btn_child_ravi" in ids(out)


@pytest.mark.asyncio
async def test_practice_launch_works_for_the_reading_move_too() -> None:
    t = await Teacher("demo3", "f").setup()
    await open_struggle_list(t, "LIT_MATRA_BLENDING", "btn_chk_most")
    await t.tap(struggle_button("LIT_AKSHAR_BY_AKSHAR"))
    await t.tap(checkin_flow.BTN_PRACTICE)
    assert (await t.ctx()).current_move_id == "LIT_MATRA_BLENDING"


@pytest.mark.asyncio
async def test_launching_practice_does_not_mark_the_skipped_learn_step_done() -> None:
    t = await Teacher("demo2", "f").setup()
    await open_struggle_list(t, "NUM_ADD_CARRY_BUNDLES", "btn_chk_some")
    await t.tap(struggle_button("NUM_ADD_CARRY"))
    await t.tap(checkin_flow.BTN_PRACTICE)
    row = t.repo._module_progress.get((t.teacher_id, "NUM_ADD_CARRY_BUNDLES"))
    assert row is None or row.learn_done_at is None


# ── idempotence ───────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tapping_the_same_struggle_twice_stores_one_check_in(lang: str) -> None:
    t = await Teacher("demo2", "f").setup()
    await open_struggle_list(t, "NUM_SUB_REGROUP_BUNDLES", "btn_chk_some")
    await t.tap(struggle_button("NUM_SUB_REGROUP"))
    again = await t.tap(struggle_button("NUM_SUB_REGROUP"))
    assert len(t.stored()) == 1
    assert alltext(again).strip() == get_message("chk_already")


@pytest.mark.asyncio
async def test_tapping_went_well_twice_stores_one_check_in(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await open_module(t, "NUM_ADD_CARRY_BUNDLES")
    await t.tap("btn_chk_well")
    again = await t.tap("btn_chk_well")
    assert len(t.stored()) == 1
    assert alltext(again).strip() == get_message("chk_already")


@pytest.mark.asyncio
async def test_the_same_check_in_again_within_the_window_is_stored_once_by_the_repository() -> None:
    repo = FakeSessionRepository()
    teacher_id = uuid4()
    first = await repo.record_class_checkin(
        teacher_id, "LIT_MATRA_BLENDING", "some", ["LIT_MATRA_DROP"]
    )
    second = await repo.record_class_checkin(
        teacher_id, "LIT_MATRA_BLENDING", "some", ["LIT_MATRA_DROP"]
    )
    assert first is not None and second is None


# ── no free text, escapes, scene, privacy ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_typing_shows_the_same_screen_again_and_stores_nothing(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    await t.tap(checkin_flow.BTN_START)
    out = await t.say("राहुल को घटाव नहीं आता")
    assert get_message("chk_pick_button") in alltext(out)
    assert module_button("LIT_MATRA_BLENDING") in ids(out)
    assert t.stored() == []
    assert (await t.ctx()).checkin_stage == "module"


@pytest.mark.asyncio
async def test_a_command_ends_the_check_in_and_runs_normally() -> None:
    t = await Teacher("demo3", "f").setup()
    await t.tap(checkin_flow.BTN_START)
    await t.say("menu")
    assert (await t.ctx()).checkin_stage == ""


@pytest.mark.asyncio
async def test_unknown_module_or_struggle_id_is_never_stored() -> None:
    t = await Teacher("demo3", "f").setup()
    await t.tap(checkin_flow.BTN_START)
    await t.tap(module_button("MADE_UP"))
    assert (await t.ctx()).checkin_stage == "module"
    await t.tap(module_button("LIT_MATRA_BLENDING"))
    await t.tap("btn_chk_some")
    await t.tap(struggle_button("NUM_COUNTING"))  # real id, but not in this module's list
    assert t.stored() == []


@pytest.mark.asyncio
async def test_the_entry_is_ignored_inside_a_scene() -> None:
    t = await Teacher("demo2", "f").setup()
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    await t.tap(checkin_flow.BTN_START)
    assert (await t.ctx()).checkin_stage == ""


@pytest.mark.asyncio
async def test_the_week_done_message_carries_the_entry_button_last(lang: str) -> None:
    t = await Teacher("demo3", "f").setup()
    ctx = await t.ctx()
    out = await t.service._week_done_messages(ctx, t.teacher_id, 3)
    assert ids(out) == ["btn_next_move", "btn_progress", checkin_flow.BTN_START]


@pytest.mark.asyncio
async def test_stored_check_in_holds_ids_only(lang: str) -> None:
    t = await Teacher("demo2", "m").setup()
    await open_struggle_list(t, "NUM_SUB_REGROUP_BUNDLES", "btn_chk_most")
    await t.tap(struggle_button("NUM_SUB_REGROUP"))
    [row] = t.stored()
    assert set(vars(row)) >= {"teacher_id", "module_id", "outcome", "struggle_ids"}
    assert not DEVANAGARI.search(row.module_id + row.outcome + "".join(row.struggle_ids))


@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
async def test_no_message_in_the_flow_uses_a_feminine_form_for_the_teacher(
    address_form: str,
) -> None:
    """The flow's own lines are neutral, so she and he read the same correct Hindi."""
    token = set_ui_lang("hi")
    try:
        t = await Teacher("demo3", address_form).setup()
        await open_struggle_list(t, "NUM_SUB_REGROUP_BUNDLES", "btn_chk_some")
        await t.tap(struggle_button("NUM_SUB_REGROUP"))
        await t.tap(checkin_flow.BTN_PRACTICE)
        text = "\n".join(line for _, lines in t.transcript for line in lines)
    finally:
        reset_ui_lang(token)
    for marker in FEMININE_MARKERS:
        assert not re.search(marker, text), marker


# ── the entry point from the chat page ────────────────────────────────────────────────────
def test_chat_page_entry_chip_is_server_rendered_with_the_existing_chip_class() -> None:
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2] / "app/web/templates/teacher.html").read_text(
        encoding="utf-8"
    )
    chip = html[html.index("checkin-entry") :].split("</section>")[0]
    assert 'class="reply-chip"' in chip and 'data-btn-id="btn_chk_start"' in chip
    assert "{% if checkin_entry %}" in html


def test_next_action_hint_while_the_check_in_is_open(lang: str) -> None:
    from backend.app.web.next_action import next_action

    for stage in ("module", "outcome", "struggle"):
        hint = next_action(
            onboarding=OnboardingStateEnum.READY.value,
            state=SessionStateEnum.DONE.value,
            context={"checkin_stage": stage},
            retries=0,
            address_form="f",
            started=True,
            scene=None,
        )
        assert hint is not None and hint["text"] == get_message("hint_checkin")
    result = next_action(
        onboarding=OnboardingStateEnum.READY.value,
        state=SessionStateEnum.DONE.value,
        context={"checkin_stage": "result"},
        retries=0,
        address_form="f",
        started=True,
        scene=None,
    )
    assert result is not None and result["key"] == "hint_done"


# ── the chat page itself (server-rendered entry, nothing added to chat.js) ──────────────────


async def _page(app: FastAPI, cookies: dict[str, str] | None = None) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return (await client.get("/teacher", cookies=cookies)).text


@pytest.mark.asyncio
@pytest.mark.parametrize("address_form", ["f", "m"])
async def test_chat_page_shows_the_entry_chip_for_an_onboarded_teacher_outside_a_scene(
    teacher_pwa_app: FastAPI,
    mock_teacher: TeacherRow,
    address_form: str,
) -> None:
    mock_teacher.onboarding_state = "READY"
    mock_teacher.address_form = address_form
    html = await _page(teacher_pwa_app)
    assert 'data-btn-id="btn_chk_start"' in html
    assert get_message("ui_checkin_entry", lang="hi") in html


@pytest.mark.asyncio
async def test_chat_page_entry_chip_label_is_english_in_the_english_ui(
    teacher_pwa_app: FastAPI,
    mock_teacher: TeacherRow,
) -> None:
    from backend.app.web.ui_lang import LANG_COOKIE_NAME, UiLangMiddleware

    mock_teacher.onboarding_state = "READY"
    teacher_pwa_app.add_middleware(UiLangMiddleware)
    html = await _page(teacher_pwa_app, {LANG_COOKIE_NAME: "en"})
    assert get_message("ui_checkin_entry", lang="en") in html


@pytest.mark.asyncio
async def test_chat_page_has_no_entry_chip_when_off_or_not_onboarded(
    teacher_pwa_app: FastAPI,
    mock_teacher: TeacherRow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_teacher.onboarding_state = "READY"
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", False)
    assert "btn_chk_start" not in await _page(teacher_pwa_app)
    monkeypatch.setattr(settings, "CLASS_CHECKIN_ENABLED", True)
    mock_teacher.onboarding_state = "NEW"
    assert "btn_chk_start" not in await _page(teacher_pwa_app)
