"""What do you want to get better at: the closed list, the classifier role, the chat flow, the
coach's lead line, the path preference and the before / after (no database)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from test_one_on_one_flow import Harness, harness, texts  # noqa: F401  (pytest fixture import)

from backend.app.class_profile import personalise, skills_flow
from backend.app.class_profile.skills import (
    OTHER_ID,
    clean_skill_ids,
    load_skills,
    skill_levels,
    skill_progress,
    skill_views,
    validate_skills,
)
from backend.app.config import settings
from backend.app.content_models import ONE_ON_ONE_CRITERIA
from backend.app.core.intents import match_intent
from backend.app.core.messages import get_message
from backend.app.llm.guards import guard_teaching_skill_classifier
from backend.app.llm.roles.teaching_skill_classifier import classify_teaching_skills
from backend.app.llm.schemas import TeachingSkillClassifierOutput
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.rule_engine.domain import Problem, TeachingAct
from backend.app.sessions.path import MovePathEntry
from backend.app.sessions.service import SessionService
from backend.app.sessions.state_machine import SessionContext, SessionStateEnum

LIB = load_skills()
IDS = LIB.ids()
CANDIDATES = {s.id: s.label_en for s in LIB.skills}
ROLE = "backend.app.llm.roles.teaching_skill_classifier.call_tool"
A = TeachingAct
SUB, ADD, PV, LIT = (
    "NUM_SUB_REGROUP_BUNDLES",
    "NUM_ADD_CARRY_BUNDLES",
    "NUM_PLACE_VALUE_BUNDLES",
    "LIT_MATRA_BLENDING",
)


def _ctx() -> SessionContext:
    return SessionContext(teacher_id="t", week_start="2026-10-19", current_move_id=SUB)


async def _say(ctx: SessionContext, text: str, button: str | None = None) -> Any:
    return await skills_flow.handle(ctx, text, button, match_intent(text=text, button_id=button))


# ── the closed list ─────────────────────────────────────────────────────────────
def test_the_list_is_the_rubric_criteria_plus_other_and_every_skill_cites_real_text() -> None:
    assert validate_skills(LIB) == []
    assert IDS == [*ONE_ON_ONE_CRITERIA, OTHER_ID]
    for s in LIB.skills:
        assert s.label_hi.strip() and s.label_en.strip()
        assert unicodedata.is_normalized("NFC", s.label_hi)
    other = LIB.get(OTHER_ID)
    assert other is not None and other.chunk_id is None and other.citation() is None
    for s in LIB.rubric_skills():
        cite = s.citation()
        assert cite is not None and cite.page is not None, s.id


def test_validation_catches_a_bad_chunk_and_a_missing_evidence_phrase(tmp_path: Path) -> None:
    text = Path(settings_path()).read_text(encoding="utf-8")
    bad = tmp_path / "skills.yaml"
    bad.write_text(
        text.replace("up_ganit_sandarshika_c1:p052:082", "no_such:p001:001", 1),
        encoding="utf-8",
    )
    assert any("is not in content/chunks" in e for e in validate_skills(load_skills(str(bad))))
    worse = tmp_path / "skills2.yaml"
    worse.write_text(
        text.replace('evidence: "facilitator"', 'evidence: "zzzz"', 1), encoding="utf-8"
    )
    assert any("not found in" in e for e in validate_skills(load_skills(str(worse))))


def settings_path() -> str:
    from backend.app.class_profile.skills import SKILLS_PATH

    return str(SKILLS_PATH)


def test_clean_ids_is_closed_distinct_capped_and_other_stands_alone() -> None:
    assert clean_skill_ids(["asks_to_explain", "BOGUS", "asks_to_explain"]) == ["asks_to_explain"]
    assert clean_skill_ids(IDS[:4]) == IDS[: settings.TEACHING_SKILLS_MAX] == IDS[:2]
    assert clean_skill_ids(["other"]) == ["other"]
    assert clean_skill_ids(["other", "probes_with_followup"]) == ["probes_with_followup"]
    assert clean_skill_ids([]) == [] and clean_skill_ids(["DROP TABLE teacher"]) == []


def test_views_carry_the_label_and_the_handbook_page() -> None:
    views = skill_views(["asks_to_explain", "other", "BOGUS"])
    assert [v.id for v in views] == ["asks_to_explain", "other"]
    assert views[0].source and views[1].source == ""


# ── the role: closed list, guarded, one retry, then the chips ───────────────────
def test_guard_accepts_only_offered_distinct_ids_within_the_limit() -> None:
    def check(ids: list[str]) -> bool:
        return guard_teaching_skill_classifier(
            TeachingSkillClassifierOutput(skill_ids=ids, confidence=0.9), IDS
        )[0]

    assert check([]) and check(IDS[:2])
    assert not check(["MADE_UP"])
    assert not check([IDS[0], IDS[0]])
    assert not check(IDS[:3])


@pytest.mark.asyncio
async def test_role_returns_ids_in_order_retries_once_then_falls_back_to_none() -> None:
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {
            "skill_ids": ["probes_with_followup", "asks_to_explain"],
            "confidence": 0.9,
        }
        assert await classify_teaching_skills("x", CANDIDATES) == [
            "probes_with_followup",
            "asks_to_explain",
        ]
        assert ct.call_count == 1
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"skill_ids": ["NOT_IN_LIST"], "confidence": 0.9}
        assert await classify_teaching_skills("x", CANDIDATES) is None
        assert ct.call_count == 2
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.side_effect = [
            {"skill_ids": ["NOT_IN_LIST"], "confidence": 0.9},
            {"skill_ids": ["asks_to_explain"], "confidence": 0.9},
        ]
        assert await classify_teaching_skills("x", CANDIDATES) == ["asks_to_explain"]
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"skill_ids": ["asks_to_explain"], "confidence": 0.1}
        assert await classify_teaching_skills("x", CANDIDATES) == []


@pytest.mark.asyncio
async def test_role_without_a_model_returns_none_and_resolve_stays_inside_the_list() -> None:
    assert await classify_teaching_skills("बच्चे से पूछना", CANDIDATES) in (None, [])  # mock LLM
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"skill_ids": ["DROP TABLE teacher"], "confidence": 1.0}
        assert await skills_flow.resolve_skills("anything") == []


# ── the chat flow ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_number_confirms_then_yes_saves_and_cites_the_handbook() -> None:
    ctx = _ctx()
    ctx.skill_stage = skills_flow.STAGE_ASKING
    res = await _say(ctx, "2")
    assert ctx.skill_stage == skills_flow.STAGE_CONFIRM and ctx.skill_pending == [IDS[1]]
    assert res.messages[0].buttons and ctx.teaching_skills == []  # nothing saved before "yes"
    res = await _say(ctx, "हाँ", "btn_yes")
    assert res.saved and ctx.teaching_skills == [IDS[1]] and ctx.skill_stage == ""
    assert res.messages[0].citations and res.messages[0].citations[0].page is not None
    assert LIB.get(IDS[1]).label_hi in (res.messages[0].text_hi or "")  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_her_words_go_through_the_classifier_and_at_most_two_are_kept() -> None:
    ctx = _ctx()
    ctx.skill_stage = skills_flow.STAGE_ASKING
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {
            "skill_ids": ["asks_to_explain", "probes_with_followup"],
            "confidence": 0.9,
        }
        res = await _say(ctx, "मैं बच्चों से पूछना और फिर सवाल करना सीखना चाहती हूँ")
    assert ctx.skill_pending == ["asks_to_explain", "probes_with_followup"]
    assert res.messages[0].buttons
    res = await _say(ctx, "", "btn_yes")
    assert ctx.teaching_skills == ["asks_to_explain", "probes_with_followup"]
    assert len(ctx.teaching_skills) <= settings.TEACHING_SKILLS_MAX


@pytest.mark.asyncio
async def test_number_replies_are_capped_at_two_and_other_stands_alone() -> None:
    ctx = _ctx()
    ctx.skill_stage = skills_flow.STAGE_ASKING
    await _say(ctx, "1, 2 और 3")
    assert ctx.skill_pending == IDS[:2]
    ctx.skill_stage = skills_flow.STAGE_ASKING
    await _say(ctx, str(len(IDS)))  # the last number is "something else"
    assert ctx.skill_pending == [OTHER_ID]
    ctx.skill_stage = skills_flow.STAGE_ASKING
    await _say(ctx, "99")  # no such number: the chips again
    assert ctx.skill_stage == skills_flow.STAGE_ASKING


@pytest.mark.asyncio
async def test_no_match_or_no_model_shows_the_chips_again_not_an_error() -> None:
    ctx = _ctx()
    ctx.skill_stage = skills_flow.STAGE_ASKING
    res = await _say(ctx, "मौसम आज बहुत अच्छा है")  # mock LLM: nothing fits
    assert ctx.skill_stage == skills_flow.STAGE_ASKING
    assert skills_flow.chip_list_text() in (res.messages[0].text_hi or "")
    assert ctx.teaching_skills == []


@pytest.mark.asyncio
async def test_skip_no_change_and_commands_end_the_question_without_storing() -> None:
    ctx = _ctx()
    ctx.teaching_skills = ["asks_to_explain"]
    ctx.skill_stage = skills_flow.STAGE_ASKING
    res = await _say(ctx, "", skills_flow.BTN_SKIP)
    assert ctx.skill_stage == "" and ctx.teaching_skills == ["asks_to_explain"]
    assert res.messages[0].text_hi == get_message("skill_skipped")
    ctx.skill_stage = skills_flow.STAGE_CONFIRM
    ctx.skill_pending = ["probes_with_followup"]
    await _say(ctx, "", "btn_no")  # "no" asks again
    assert ctx.skill_stage == skills_flow.STAGE_ASKING and ctx.teaching_skills == [
        "asks_to_explain"
    ]
    res = await _say(ctx, "menu")  # a command is not an answer: handled elsewhere
    assert not res.handled and ctx.skill_stage == ""


@pytest.mark.asyncio
async def test_after_the_class_choice_is_saved_the_skill_question_follows_in_chat() -> None:
    from test_state_machine import FakeSessionRepository

    from backend.app.core.types import InboundMessage
    from backend.app.sessions.state_machine import OnboardingStateEnum

    repo = FakeSessionRepository()
    service = SessionService(repository=repo)
    teacher_id = uuid4()
    teacher = await repo.get_or_create_teacher(teacher_id)
    teacher.onboarding_state = OnboardingStateEnum.READY.value
    await repo.save_teacher(teacher)
    ctx = await service.get_or_create_context(teacher_id)
    ctx.onboarding_state = OnboardingStateEnum.READY
    ctx.current_state = SessionStateEnum.LEARN
    await service._sync_context_to_db(ctx, teacher_id)

    async def say(text: str | None = None, button: str | None = None) -> list[Any]:
        from datetime import UTC, datetime

        return await service.handle_inbound(
            InboundMessage(
                channel="web",
                channel_msg_id=f"m-{uuid4().hex[:8]}",
                teacher_id=teacher_id,
                kind="button" if button else "text",
                text=text,
                button_id=button,
                received_at=datetime.now(UTC),
            )
        )

    await say("मेरी कक्षा")
    await say("5")  # a chip number
    saved = await say(button="btn_yes")
    body = texts(saved)
    assert get_message("skill_ask", "f", list=skills_flow.chip_list_text(), max=2) in body
    ctx = await service.get_or_create_context(teacher_id)
    assert ctx.skill_stage == skills_flow.STAGE_ASKING and ctx.class_struggles
    await say("1")
    done = await say(button="btn_yes")
    ctx = await service.get_or_create_context(teacher_id)
    assert ctx.teaching_skills == [IDS[0]] and ctx.skill_stage == ""
    assert (await repo.get_or_create_teacher(teacher_id)).teaching_skills == [IDS[0]]
    assert done[0].citations


# ── the coach leads with her skill ──────────────────────────────────────────────
def test_lead_line_uses_the_rubric_wording_for_the_level_she_reached() -> None:
    move = load_move_card(SUB)
    ctx = _ctx()
    ctx.teaching_skills = ["asks_to_explain", "other"]
    scores = {"asks_to_explain": 2, "does_not_tell_answer": 0}
    lead = SessionService._skill_lead(move, scores, ctx, "f")
    crit = next(c for c in move.rubric_one_on_one.criteria if c.id == "asks_to_explain")  # type: ignore[union-attr]
    assert crit.levels[2] in lead
    assert LIB.get("asks_to_explain").label_hi in lead  # type: ignore[union-attr]
    assert "(2/2)" in lead and lead.count("\n") == 0  # "other" adds nothing
    ctx.teaching_skills = []
    assert SessionService._skill_lead(move, scores, ctx, "f") == ""
    ctx.teaching_skills = ["asks_to_explain"]
    assert SessionService._skill_lead(move, {"crit_other": 2}, ctx, "f") == ""  # not scored


def test_skill_levels_ignore_unscored_and_out_of_range_values() -> None:
    move = load_move_card(SUB)
    out = skill_levels(
        move,
        {"asks_to_explain": 7, "probes_with_followup": {"score": 1}, "checks_on_new_problem": True},
        ["asks_to_explain", "probes_with_followup", "checks_on_new_problem", "other"],
    )
    assert [(o.skill_id, o.level) for o in out] == [
        ("asks_to_explain", settings.SKILL_LEVEL_MAX),
        ("probes_with_followup", 1),
    ]
    assert skill_levels(load_move_card(LIT), {"asks_to_explain": 2}, ["asks_to_explain"]) == []


@pytest.mark.asyncio
async def test_feedback_begins_with_her_skill_and_the_scores_come_from_the_coach(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(ADD)
    ctx = await h.ctx()
    ctx.teaching_skills = ["asks_to_explain"]
    await h.service._sync_context_to_db(ctx, h.teacher_id)
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
    label = LIB.get("asks_to_explain").label_hi  # type: ignore[union-attr]
    marker = get_message("coach_skill_lead", "f", label=label, level_text="", level=0, max=2)
    prefix = marker.split(label)[0]
    assert prefix in body and label in body
    (score,) = h.service.repo._rehearsal_scores
    level = score.scores["asks_to_explain"]
    assert f"({level}/{settings.SKILL_LEVEL_MAX})" in body
    assert body.index(label) < body.index(score.strength_hi)  # leads, before the usual feedback


# ── the path prefers moves that score her skill ─────────────────────────────────
def _path(*moves: str) -> list[MovePathEntry]:
    return [MovePathEntry(i, m, f"month_rank={i}") for i, m in enumerate(moves, start=1)]


def test_path_puts_moves_whose_rubric_scores_her_skill_before_the_others_and_restores() -> None:
    original = _path(LIT, PV, SUB)
    out = personalise.order_path(original, [], skill_ids=["asks_to_explain"])
    assert [e.move_id for e in out] == [PV, SUB, LIT]
    assert personalise.rubric_scores_skill(SUB, ["asks_to_explain"])
    assert not personalise.rubric_scores_skill(LIT, ["asks_to_explain"])
    assert not personalise.rubric_scores_skill(SUB, ["other"])
    assert not personalise.rubric_scores_skill("NO_SUCH_MOVE", ["asks_to_explain"])
    back = personalise.order_path(out, [], skill_ids=[])
    assert [e.move_id for e in back] == [LIT, PV, SUB]


def test_a_class_struggle_move_still_comes_before_a_skill_move() -> None:
    out = personalise.order_path(
        _path(PV, LIT, SUB), ["LIT_MATRA_DROP"], skill_ids=["asks_to_explain"]
    )
    assert [e.move_id for e in out] == [LIT, PV, SUB]


# ── before / after ──────────────────────────────────────────────────────────────
def test_before_after_needs_two_scored_scenes_and_ignores_other_and_unscored() -> None:
    first = {"asks_to_explain": 0, "does_not_tell_answer": 2}
    later = {"asks_to_explain": 2, "does_not_tell_answer": 1}
    one = skill_progress([(SUB, first)], ["asks_to_explain", "other"])
    assert [p.skill_id for p in one] == ["asks_to_explain"]
    assert one[0].n_scenes == 1 and not one[0].ready and one[0].first_level is None
    two = skill_progress([(SUB, first), (ADD, later)], ["asks_to_explain"])
    assert two[0].ready and (two[0].first_level, two[0].last_level) == (0, 2)
    crit = {c.id: c for c in load_move_card(SUB).rubric_one_on_one.criteria}  # type: ignore[union-attr]
    assert two[0].first_text_hi == crit["asks_to_explain"].levels[0]
    none = skill_progress([(SUB, {"crit_x": 1}), (LIT, {})], ["asks_to_explain"])
    assert none[0].n_scenes == 0 and not none[0].ready
    assert skill_progress([(SUB, first), (SUB, later)], []) == []


# ── no LLM output changes what a child answers ──────────────────────────────────
async def _scene(h: Harness, skills: list[str]) -> list[Any]:
    await h.start(ADD)
    ctx = await h.ctx()
    ctx.teaching_skills = skills
    await h.service._sync_context_to_db(ctx, h.teacher_id)
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
async def test_her_skill_and_a_hostile_classifier_never_change_a_childs_answer(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    baseline = await _scene(harness(), [])
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"skill_ids": ["does_not_tell_answer"], "confidence": 1.0}
        chosen = await _scene(harness(), ["asks_to_explain", "does_not_tell_answer"])
    assert baseline and chosen == baseline


def test_the_rule_engine_does_not_know_about_skills_the_class_profile_or_any_model() -> None:
    engine_dir = Path(__file__).resolve().parents[3] / "backend" / "app" / "rule_engine"
    pattern = re.compile(r"teaching_skill|class_profile|backend\.app\.llm|anthropic", re.IGNORECASE)
    for path in engine_dir.rglob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name
