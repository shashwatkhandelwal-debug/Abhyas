"""Part 4: her class choice -> path order, "chosen because", scene focus child, "did it help".

The central claim is also tested here: no LLM output (voice line, classifier, tagger text) changes
what a simulated child answers; the rule engine alone decides.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from test_one_on_one_flow import Harness, harness, texts  # noqa: F401  (pytest fixture import)

from backend.app.class_profile import flow, personalise
from backend.app.class_profile.library import load_library
from backend.app.core.messages import get_message
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.rule_engine.domain import Problem, TeachingAct
from backend.app.sessions.modules import module_views
from backend.app.sessions.path import MovePathEntry
from backend.app.sessions.state_machine import SessionStateEnum

A = TeachingAct
LIB = load_library()
SUB, ADD, PV, LIT = (
    "NUM_SUB_REGROUP_BUNDLES",
    "NUM_ADD_CARRY_BUNDLES",
    "NUM_PLACE_VALUE_BUNDLES",
    "LIT_MATRA_BLENDING",
)


def _path(*moves: str) -> list[MovePathEntry]:
    return [MovePathEntry(i, m, f"month_rank={i}") for i, m in enumerate(moves, start=1)]


# ── path order ──────────────────────────────────────────────────────────────────
def test_struggle_moves_come_first_in_her_order_and_the_rest_keep_theirs() -> None:
    out = personalise.order_path(_path(PV, SUB, ADD, LIT), ["NUM_ADD_CARRY", "LIT_MATRA_DROP"])
    assert [e.move_id for e in out] == [ADD, LIT, PV, SUB]
    assert [e.position for e in out] == [1, 2, 3, 4]
    assert "matches_class_struggle=NUM_ADD_CARRY" in out[0].reason
    assert "matches_class_struggle" not in out[2].reason


def test_two_struggles_on_one_move_count_once_and_unknown_ids_are_ignored() -> None:
    out = personalise.order_path(
        _path(PV, SUB, ADD), ["BOGUS", "NUM_SUB_REGROUP", "NUM_SUB_REGROUP"]
    )
    assert [e.move_id for e in out] == [SUB, PV, ADD]


def test_clearing_the_choice_restores_the_original_order() -> None:
    original = _path(PV, SUB, ADD, LIT)
    chosen = personalise.order_path(original, ["LIT_MATRA_DROP"])
    changed = personalise.order_path(chosen, ["NUM_SUB_REGROUP"])  # change, not just add
    assert [e.move_id for e in changed][0] == SUB
    restored = personalise.order_path(changed, [])
    assert [e.move_id for e in restored] == [PV, SUB, ADD, LIT]
    assert all("matches_class_struggle" not in e.reason for e in restored)
    assert personalise.order_path(restored, []) == restored  # idempotent


def test_a_completed_move_is_not_pulled_to_the_front() -> None:
    out = personalise.order_path(
        _path(PV, SUB, ADD), ["NUM_ADD_CARRY", "NUM_SUB_REGROUP"], done_moves=frozenset({ADD})
    )
    assert [e.move_id for e in out] == [SUB, PV, ADD]


def test_because_names_the_top_struggle_the_move_practises() -> None:
    assert personalise.because(ADD, ["NUM_COUNTING", "NUM_ADD_CARRY"]) is not None
    found = personalise.because(PV, ["NUM_NUMBER_WRITING", "NUM_PLACE_VALUE"])
    assert found is not None and found.id == "NUM_NUMBER_WRITING"
    assert personalise.because(SUB, ["NUM_COUNTING", "LIT_COMPREHENSION"]) is None
    assert personalise.because(SUB, []) is None


def test_module_picker_puts_her_struggle_modules_first_with_the_reason() -> None:
    plain = module_views({})
    assert [v.because for v in plain] == ["", "", ""]
    chosen = module_views({}, ["NUM_PLACE_VALUE", "NUM_ADD_CARRY"])
    assert [v.module_id for v in chosen] == [PV, ADD, SUB]
    assert chosen[0].because and chosen[1].because and chosen[2].because == ""


# ── the focus child ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("move_id", "struggles", "child", "misconception"),
    [
        (ADD, ["NUM_ADD_CARRY"], "ravi", "ADD_CARRY_FORGOTTEN"),
        (PV, ["NUM_PLACE_VALUE"], "priya", "PV_BUNDLE_AS_ONE"),
        (PV, ["NUM_COUNTING", "NUM_NUMBER_WRITING"], "aman", "PV_CONCAT_SPOKEN"),
        (SUB, ["NUM_SUB_REGROUP"], "ravi", "SUB_SMALLER_FROM_LARGER"),
    ],
)
def test_focus_child_is_the_one_with_the_matching_misconception(
    move_id: str, struggles: list[str], child: str, misconception: str
) -> None:
    focus = personalise.focus_child(load_move_card(move_id), struggles)
    assert focus is not None
    assert (focus.persona_id, focus.misconception_id) == (child, misconception)


def test_no_focus_child_when_the_move_does_not_practise_her_struggle() -> None:
    move = load_move_card(SUB)
    assert personalise.focus_child(move, []) is None
    assert personalise.focus_child(move, ["NUM_ADD_CARRY", "LIT_MATRA_DROP"]) is None


# ── scenes ──────────────────────────────────────────────────────────────────────
async def _choose_class(h: Harness, struggles: list[str]) -> None:
    ctx = await h.ctx()
    ctx.class_struggles = struggles
    await h.service._sync_context_to_db(ctx, h.teacher_id)


@pytest.mark.asyncio
async def test_one_on_one_child_choice_puts_the_matching_child_first(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(ADD)
    await _choose_class(h, ["NUM_ADD_CARRY"])
    await h.say(button="btn_listen")
    out = await h.say(button="btn_rehearse_one")
    buttons = out[0].buttons
    assert [b.id for b in buttons][0] == "btn_child_ravi"
    assert buttons[0].title_hi.startswith("★")
    assert not buttons[1].title_hi.startswith("★")
    assert {b.id for b in buttons} == {"btn_child_ravi", "btn_child_priya", "btn_child_aman"}
    assert "आपकी कक्षा की दिक्कत" in (out[0].text_hi or "")


@pytest.mark.asyncio
async def test_without_a_matching_struggle_the_children_are_unchanged(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(ADD)
    await _choose_class(h, ["LIT_COMPREHENSION"])
    await h.say(button="btn_listen")
    out = await h.say(button="btn_rehearse_one")
    assert [b.id for b in out[0].buttons] == ["btn_child_ravi", "btn_child_priya", "btn_child_aman"]
    assert not any(b.title_hi.startswith("★") for b in out[0].buttons)
    assert "आपकी कक्षा की दिक्कत" not in (out[0].text_hi or "")


@pytest.mark.asyncio
async def test_group_scene_names_the_child_with_her_class_mistake(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(PV)
    await _choose_class(h, ["NUM_PLACE_VALUE"])
    await h.say(button="btn_listen")
    out = await h.say(button="btn_rehearse_group")
    assert get_message("speaker_priya") in texts(out) and "आपकी कक्षा की दिक्कत" in texts(out)


@pytest.mark.asyncio
async def test_coach_feedback_mentions_her_class_struggle(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(ADD)
    await _choose_class(h, ["NUM_ADD_CARRY"])
    await h.say(button="btn_listen")
    await h.say(button="btn_rehearse_one")
    await h.say(button="btn_child_ravi")
    await h.say("हासिल जोड़ना भूल गया")
    h.script += [
        ([A.ASK_TO_EXPLAIN], None, None),
        ([A.CONCRETE_REPRESENTATION], None, None),
        ([A.CONTRAST_TWO_ANSWERS], None, None),
        ([A.GIVE_NEW_PROBLEM], None, Problem(type="add", a=27, b=48)),
    ]
    out: list[Any] = []
    for line in ("कैसे किया?", "बंडल देखो और गिनो।", "कौन सा सही है?", "अब यह नया सवाल करो।"):
        out = await h.say(line)
    body = texts(out)
    assert get_message("feedback_header", "f") in body
    link = get_message(
        "coach_class_link",
        "f",
        label=LIB.get("NUM_ADD_CARRY").label_hi,  # type: ignore[union-attr]
        child=get_message("speaker_ravi"),
    )
    assert link in body
    # the link comes before the retry / continue question and is not part of the coach scores
    assert body.index(link) < body.index(get_message("realism_prompt", "f"))


# ── no LLM output changes what a child answers ──────────────────────────────────
async def _scripted_scene(h: Harness, struggles: list[str]) -> list[Any]:
    await h.start(ADD)
    await _choose_class(h, struggles)
    await h.say(button="btn_listen")
    await h.say(button="btn_rehearse_one")
    await h.say(button="btn_child_ravi")
    await h.say("हासिल जोड़ना भूल गया")
    h.script += [
        ([A.ASK_TO_EXPLAIN], None, None),
        ([A.CONCRETE_REPRESENTATION], None, None),
        ([A.GIVE_NEW_PROBLEM], None, Problem(type="add", a=27, b=48)),
    ]
    for line in ("कैसे किया?", "बंडल देखो और गिनो।", "अब यह नया सवाल करो।"):
        await h.say(line)
    scene = next(iter(h.store._scenes.values()))
    return [t.child_responses for t in scene.turns]


@pytest.mark.asyncio
async def test_hostile_llm_output_and_a_class_profile_never_change_a_childs_answer(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    baseline = await _scripted_scene(harness(), [])
    personalised = await _scripted_scene(harness(), ["NUM_ADD_CARRY", "LIT_MATRA_DROP"])
    assert baseline and personalised == baseline  # her profile changes no answer

    hostile_line = {"line_hi": "नौ सौ निन्यानवे! मैंने सही किया।"}
    hostile_classifier = {"struggle_ids": ["NUM_COUNTING"], "confidence": 1.0}
    with (
        patch("backend.app.llm.roles.child_voice.call_tool", new_callable=AsyncMock) as voice,
        patch(
            "backend.app.llm.roles.class_struggle_classifier.call_tool", new_callable=AsyncMock
        ) as classifier,
    ):
        voice.return_value = hostile_line
        classifier.return_value = hostile_classifier
        h = harness()
        attacked = await _scripted_scene(h, ["NUM_ADD_CARRY"])
        spoken = [
            line.line_hi
            for scene in h.store._scenes.values()
            for turn in scene.turns
            for line in turn.child_lines
        ]
    assert attacked == baseline  # same rule-engine answers whatever the model said
    assert voice.call_count >= 1
    assert all("999" not in s and "नौ सौ" not in s for s in spoken)  # the guard dropped the lie
    assert spoken  # the children did speak, from the template fallback


# ── "did it help your class?" ───────────────────────────────────────────────────
async def _at_end_of_reflection(h: Harness, struggles: list[str]) -> list[Any]:
    await h.start(ADD)
    ctx = await h.ctx()
    ctx.class_struggles = struggles
    ctx.current_state = SessionStateEnum.DONE
    return await h.service._begin_training_rating(ctx, h.teacher_id, 2)


@pytest.mark.asyncio
async def test_helped_question_is_asked_only_when_the_move_practises_her_struggle(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    out = await _at_end_of_reflection(h, ["NUM_ADD_CARRY"])
    assert [b.id for b in out[0].buttons] == ["btn_helped_yes", "btn_helped_some", "btn_helped_no"]
    assert (await h.ctx()).rating_stage == "helped"

    h2 = harness()
    out = await _at_end_of_reflection(h2, ["LIT_COMPREHENSION"])
    assert out[0].text_hi == get_message("rate_training_prompt", "f")
    assert (await h2.ctx()).rating_stage == "rating"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("said", "button", "expected"),
    [
        (None, "btn_helped_yes", "yes"),
        (None, "btn_helped_some", "some"),
        (None, "btn_helped_no", "no"),
        ("हाँ, बहुत मदद मिली", None, "yes"),
        ("थोड़ी मिली", None, "some"),
        ("नहीं मिली", None, "no"),
        ("it helped", None, "yes"),
    ],
)
async def test_helped_answer_is_stored_as_evidence_then_the_rating_follows(
    harness: Callable[[], Harness],  # noqa: F811
    said: str | None,
    button: str | None,
    expected: str,
) -> None:
    h = harness()
    await _at_end_of_reflection(h, ["NUM_ADD_CARRY", "NUM_COUNTING"])
    out = await h.say(said, button)
    assert get_message("class_helped_thanks", "f") in texts(out)
    assert get_message("rate_training_prompt", "f") in texts(out)
    (row,) = h.service.repo._class_outcomes  # type: ignore[attr-defined]
    assert (row.answer, row.move_id, row.struggle_ids) == (
        expected,
        ADD,
        ["NUM_ADD_CARRY", "NUM_COUNTING"],
    )
    assert (await h.ctx()).rating_stage == "rating"


@pytest.mark.asyncio
async def test_unclear_helped_replies_never_trap_and_store_nothing(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await _at_end_of_reflection(h, ["NUM_ADD_CARRY"])
    first = await h.say("पता नहीं क्या कहूँ ??")  # contains "नहीं" -> a real answer
    assert h.service.repo._class_outcomes  # type: ignore[attr-defined]
    assert get_message("rate_training_prompt", "f") in texts(first)

    h2 = harness()
    await _at_end_of_reflection(h2, ["NUM_ADD_CARRY"])
    again = await h2.say("hmm")
    assert [b.id for b in again[0].buttons] == [
        "btn_helped_yes",
        "btn_helped_some",
        "btn_helped_no",
    ]
    skipped = await h2.say("???")
    assert get_message("rate_training_prompt", "f") in texts(skipped)
    assert h2.service.repo._class_outcomes == []  # type: ignore[attr-defined]


def test_parse_helped_words() -> None:
    assert flow.parse_helped("", "btn_helped_no") == "no"
    assert flow.parse_helped("थोड़ा बहुत", None) == "some"
    assert flow.parse_helped("बिलकुल नहीं", None) == "no"
    assert flow.parse_helped("hello", None) is None
    assert uuid4()  # keeps the import used when the module is edited


@pytest.mark.asyncio
async def test_invite_after_onboarding_then_the_choice_reorders_her_path() -> None:
    """New teacher -> placement -> the optional invite -> buttons -> words -> yes -> path."""
    from test_state_machine import FakeSessionRepository, make_inbound

    from backend.app.sessions.service import SessionService

    service = SessionService(repository=FakeSessionRepository())
    t_id = uuid4()
    steps: list[tuple[str | None, str | None]] = [
        ("सहमत हूँ", "btn_agree"),
        ("KNP-C01-B1", None),
        ("सुनीता शर्मा", None),
        ("शिक्षिका", "btn_female"),
        ("0-1 साल", None),
        ("कक्षा 1-2", None),
        ("हाँ", "btn_yes"),
        ("रवि, 52 में से 17 घटाना है।", None),
    ]
    for text, button in steps:
        await service.handle_inbound(make_inbound(t_id, text, button))
    done = await service.handle_inbound(make_inbound(t_id, "रवि, 52 में 5 बंडल और 2 तीलियाँ हैं।"))
    invite = done[-1]
    assert [b.id for b in invite.buttons] == ["btn_cls_start", "btn_cls_skip"]
    teacher = await service.repo.get_or_create_teacher(t_id)
    assert teacher.class_profile_prompted_at is not None and not teacher.class_struggles
    first_before = (await service.repo.get_move_path(t_id))[0].move_id
    assert first_before != LIT  # the matra move is not first until she says so

    asked = await service.handle_inbound(make_inbound(t_id, None, "btn_cls_start"))
    assert "कहाँ अटक" in (asked[0].text_hi or "")
    confirm = await service.handle_inbound(make_inbound(t_id, "मात्रा छोड़कर पढ़ते हैं"))
    assert confirm[0].buttons[0].id == "btn_yes"
    await service.handle_inbound(make_inbound(t_id, None, "btn_yes"))
    assert teacher.class_struggles == ["LIT_MATRA_DROP"]
    path = await service.repo.get_move_path(t_id)
    assert path[0].move_id == LIT and "matches_class_struggle=LIT_MATRA_DROP" in (
        path[0].reason or ""
    )
    assert [p.position for p in path] == list(range(1, len(path) + 1))
    ctx = await service.get_or_create_context(t_id)
    assert ctx.current_state == SessionStateEnum.LEARN  # the week in progress is not switched

    await service.set_class_struggles(t_id, [])
    restored = await service.repo.get_move_path(t_id)
    assert restored[0].move_id == first_before


@pytest.mark.parametrize(
    "module",
    [
        "backend.app.class_profile.personalise",
        "backend.app.class_profile.flow",
        "backend.app.db.seed",
    ],
)
def test_class_profile_modules_import_first_without_a_cycle(module: str) -> None:
    """A fresh process that imports one of these first must not hit a circular import."""
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).resolve().parents[3],
    )
    assert result.returncode == 0, result.stderr[-800:]
