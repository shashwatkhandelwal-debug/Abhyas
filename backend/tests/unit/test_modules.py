"""Part 6: module registry, module_check role (schema, guard, retry, fallback) and the flow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from test_one_on_one_flow import CASES, A, Harness, harness, texts  # noqa: F401  (fixture)

from backend.app.config import settings
from backend.app.core.messages import get_message
from backend.app.llm.guards import guard_module_check
from backend.app.llm.roles.module_check import check_module, keyword_covered
from backend.app.llm.schemas import ModuleCheckOutput
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.rule_engine.domain import Problem
from backend.app.sessions import modules
from backend.app.sessions.state_machine import SessionStateEnum

SUB = "NUM_SUB_REGROUP_BUNDLES"
MOVE = load_move_card(SUB)
GOOD_ANSWER = (
    "मैं पहले बच्चे से पूछूँगा कि उसने कैसे किया, फिर बंडल और तीलियों से दिखाऊँगा, "
    "और उत्तर खुद नहीं बताऊँगा, दो उत्तरों की तुलना करवाऊँगा।"
)


def test_registry_lists_the_three_numeracy_modules_subtraction_first() -> None:
    ids = modules.module_ids()
    assert ids[0] == SUB and len(ids) == 3
    for mid in ids:
        card = modules.module_card(mid)
        assert card.rubric_one_on_one is not None and card.key_points
    views = modules.module_views({})
    assert [v.module_id for v in views] == ids
    assert all(not v.complete and v.next_step == "learn" and v.steps_done == 0 for v in views)


# ── module_check ─────────────────────────────────────────────────────────────
def test_guard_accepts_real_ids_and_a_short_respectful_reply() -> None:
    ok = ModuleCheckOutput(covered_point_ids=["kp1", "kp2"], reply_hi="बहुत अच्छा, आपने पूछना बताया।")
    assert guard_module_check(ok, ["kp1", "kp2", "kp3"])[0]


@pytest.mark.parametrize(
    ("output", "why"),
    [
        (ModuleCheckOutput(covered_point_ids=["kpX"], reply_hi="ठीक है"), "not in the module"),
        (ModuleCheckOutput(covered_point_ids=["kp1", "kp1"], reply_hi="ठीक है"), "duplicates"),
        (ModuleCheckOutput(covered_point_ids=["kp1"], reply_hi=""), "Empty"),
        (ModuleCheckOutput(covered_point_ids=["kp1"], reply_hi="शब्द " * 60), "exceeds"),
        (ModuleCheckOutput(covered_point_ids=["kp1"], reply_hi="तुम बहुत अच्छे हो"), "Disrespect"),
    ],
)
def test_guard_rejects(output: ModuleCheckOutput, why: str) -> None:
    ok, reason = guard_module_check(output, ["kp1", "kp2", "kp3"])
    assert not ok and why in reason


@pytest.mark.asyncio
async def test_check_passes_from_the_covered_ids_not_from_the_model() -> None:
    must = [kp.id for kp in MOVE.key_points if kp.must_have]
    payload = {"covered_point_ids": must, "reply_hi": "बहुत अच्छा।"}
    with patch("backend.app.llm.roles.module_check.call_tool", new_callable=AsyncMock) as ct:
        ct.return_value = payload
        res = await check_module(MOVE, GOOD_ANSWER, "q")
    assert res.passed and not res.used_fallback and res.covered == must
    one = {"covered_point_ids": must[:1], "reply_hi": "ठीक।"}
    with patch("backend.app.llm.roles.module_check.call_tool", new_callable=AsyncMock) as ct:
        ct.return_value = one
        res = await check_module(MOVE, GOOD_ANSWER, "q")
    assert settings.MODULE_CHECK_PASS_MUST_HAVE == 2 and not res.passed


@pytest.mark.asyncio
async def test_unknown_ids_are_retried_once_then_the_keyword_fallback_is_used() -> None:
    bad = {"covered_point_ids": ["made_up"], "reply_hi": "ठीक।"}
    with patch("backend.app.llm.roles.module_check.call_tool", new_callable=AsyncMock) as ct:
        ct.return_value = bad
        res = await check_module(MOVE, GOOD_ANSWER, "q")
    assert ct.call_count == 2 and res.used_fallback
    assert res.covered == keyword_covered(MOVE, GOOD_ANSWER) and res.covered


@pytest.mark.asyncio
async def test_too_short_an_answer_is_not_sent_to_the_model_and_does_not_pass() -> None:
    with patch("backend.app.llm.roles.module_check.call_tool", new_callable=AsyncMock) as ct:
        res = await check_module(MOVE, "पता नहीं", "q")
    ct.assert_not_called()
    assert not res.passed and res.used_fallback
    assert res.reply_hi.startswith(get_message("module_check_reply_more", "f", point="X")[:6])


# ── flow ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_picker_start_then_steps_are_tracked_through_the_check(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(SUB)
    out = await h.service.start_module(h.teacher_id, SUB)
    assert out[0].buttons and out[0].buttons[0].id == "btn_understood"
    ctx = await h.ctx()
    assert ctx.module_mode and ctx.current_state == SessionStateEnum.LEARN
    assert not await h.service.repo.get_module_progress(h.teacher_id)

    # learn -> explain back -> model -> mode -> child -> diagnosis -> scene -> feedback
    ctx.current_state = SessionStateEnum.MODEL
    await h.service._sync_context_to_db(ctx, h.teacher_id)
    await h.say(button="btn_listen")
    await h.say(button="btn_rehearse_one")
    await h.say(button="btn_child_ravi")
    await h.say("उल्टा घटा दिया")
    (row,) = await h.service.repo.get_module_progress(h.teacher_id)
    flags = modules.step_flags(row)
    assert flags == {"learn": True, "diagnose": True, "practise": False, "check": False}
    assert row.diagnose_verdict == "correct"

    h.script += [
        ([A.ASK_TO_EXPLAIN], None, None),
        ([A.CONCRETE_REPRESENTATION], None, None),
        ([A.CONTRAST_TWO_ANSWERS], None, None),
        ([A.GIVE_NEW_PROBLEM], None, Problem(type="sub", a=52, b=17)),
    ]
    for line in ("कैसे किया?", "बंडल देखो", "कौन सही?", "नया सवाल करो"):
        await h.say(line)
    assert (await h.ctx()).current_state == SessionStateEnum.FEEDBACK
    (row,) = await h.service.repo.get_module_progress(h.teacher_id)
    assert modules.step_flags(row)["practise"] and not modules.step_flags(row)["check"]

    # continue -> the closing check question (not the try-in-class step yet)
    out = await h.say(button="btn_continue")
    assert out[0].text_hi == get_message("module_check_prompt", "f", move_title=MOVE.title_hi)
    ctx = await h.ctx()
    assert ctx.current_state == SessionStateEnum.FEEDBACK and ctx.module_check_stage == "asking"

    out = await h.say(GOOD_ANSWER)  # mock LLM -> guarded fallback judges by keywords
    (row,) = await h.service.repo.get_module_progress(h.teacher_id)
    flags = modules.step_flags(row)
    assert all(flags.values()) and row.check_passed is True and row.check_covered
    assert out[-1].buttons and out[-1].buttons[0].id == "btn_continue"

    out = await h.say(button="btn_continue")  # now the loop goes on as usual
    assert (await h.ctx()).current_state == SessionStateEnum.TRY_IN_CLASS
    assert "कक्षा" in texts(out)


@pytest.mark.asyncio
async def test_skipping_the_check_leaves_the_module_open(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(SUB)
    await h.service.start_module(h.teacher_id, SUB)
    ctx = await h.ctx()
    ctx.current_state = SessionStateEnum.FEEDBACK
    ctx.module_check_stage = "asking"
    await h.service._sync_context_to_db(ctx, h.teacher_id)
    await h.say(button="btn_continue")
    assert (await h.ctx()).module_check_stage == "done"
    rows: list[Any] = await h.service.repo.get_module_progress(h.teacher_id)
    assert not any(modules.step_flags(r)["check"] for r in rows)


@pytest.mark.asyncio
async def test_start_module_rejects_unknown_ids(
    harness: Callable[[], Harness],  # noqa: F811
) -> None:
    h = harness()
    await h.start(SUB)
    with pytest.raises(ValueError):
        await h.service.start_module(h.teacher_id, "NOT_A_MODULE")


def test_cases_exist_for_every_module() -> None:
    assert {c[0] for c in CASES} == set(modules.module_ids())
