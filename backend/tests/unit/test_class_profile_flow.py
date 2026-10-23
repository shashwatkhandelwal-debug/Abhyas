"""The class_struggle_classifier role and the "My class" chat flow (no database)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.class_profile import flow
from backend.app.class_profile.library import load_library
from backend.app.config import settings
from backend.app.core.intents import Intent, match_intent
from backend.app.llm.guards import guard_class_struggle_classifier
from backend.app.llm.roles.class_struggle_classifier import classify_class_struggles
from backend.app.llm.schemas import ClassStruggleClassifierOutput
from backend.app.sessions.state_machine import SessionContext

LIB = load_library()
IDS = LIB.ids()
CANDIDATES = {s.id: s.label_en for s in LIB.struggles}
ROLE = "backend.app.llm.roles.class_struggle_classifier.call_tool"


def _ctx() -> SessionContext:
    return SessionContext(
        teacher_id="t", week_start="2026-10-19", current_move_id="NUM_SUB_REGROUP_BUNDLES"
    )


async def _say(ctx: SessionContext, text: str, button: str | None = None) -> flow.FlowResult:
    return await flow.handle(ctx, text, button, match_intent(text=text, button_id=button))


# ── the role ────────────────────────────────────────────────────────────────────
def test_guard_accepts_only_offered_distinct_ids_within_the_limit() -> None:
    def check(ids: list[str]) -> bool:
        return guard_class_struggle_classifier(
            ClassStruggleClassifierOutput(struggle_ids=ids, confidence=0.9), IDS
        )[0]

    assert check([])
    assert check([IDS[0], IDS[1], IDS[2]])
    assert not check(["MADE_UP"])
    assert not check([IDS[0], IDS[0]])
    assert not check(IDS[: settings.STRUGGLE_MAX_CHOSEN + 1])


@pytest.mark.asyncio
async def test_role_returns_the_ids_in_order() -> None:
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"struggle_ids": ["NUM_ADD_CARRY", "NUM_COUNTING"], "confidence": 0.9}
        assert await classify_class_struggles("x", CANDIDATES) == ["NUM_ADD_CARRY", "NUM_COUNTING"]
        assert ct.call_count == 1


@pytest.mark.asyncio
async def test_role_retries_once_then_falls_back_when_the_model_invents_an_id() -> None:
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"struggle_ids": ["NOT_IN_LIST"], "confidence": 0.9}
        assert await classify_class_struggles("x", CANDIDATES) is None
        assert ct.call_count == 2
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.side_effect = [
            {"struggle_ids": ["NOT_IN_LIST"], "confidence": 0.9},
            {"struggle_ids": ["NUM_COUNTING"], "confidence": 0.9},
        ]
        assert await classify_class_struggles("x", CANDIDATES) == ["NUM_COUNTING"]


@pytest.mark.asyncio
async def test_role_low_confidence_means_nothing_fits() -> None:
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"struggle_ids": ["NUM_COUNTING"], "confidence": 0.1}
        assert await classify_class_struggles("x", CANDIDATES) == []


@pytest.mark.asyncio
async def test_resolve_never_returns_an_id_outside_the_library() -> None:
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"struggle_ids": ["DROP TABLE teacher"], "confidence": 1.0}
        res = await flow.resolve_struggles("बच्चे गिनती में गलती करते हैं")
    assert res.source == "keywords"
    assert set(res.ids) <= set(IDS)


@pytest.mark.asyncio
async def test_resolve_on_the_mock_llm_uses_the_keyword_matcher() -> None:
    res = await flow.resolve_struggles("हासिल भूल जाते हैं बच्चे")
    assert (res.ids, res.source) == (["NUM_ADD_CARRY"], "keywords")
    assert (await flow.resolve_struggles("मौसम अच्छा है")).source == "none"
    assert (await flow.resolve_struggles("   ")).ids == []


@pytest.mark.asyncio
async def test_resolve_prefers_the_classifier_when_it_answers() -> None:
    with patch(ROLE, new_callable=AsyncMock) as ct:
        ct.return_value = {"struggle_ids": ["LIT_COMPREHENSION"], "confidence": 0.9}
        res = await flow.resolve_struggles("kuch bhi")
    assert (res.ids, res.source) == (["LIT_COMPREHENSION"], "llm")


# ── the conversation ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_command_starts_the_question_with_numbered_chips() -> None:
    ctx = _ctx()
    res = await _say(ctx, "मेरी कक्षा")
    assert res.handled and ctx.class_stage == flow.STAGE_ASKING
    text = res.messages[0].text_hi or ""
    assert "1. " in text and f"{len(LIB.chips()) + 1}. " in text
    assert res.messages[0].buttons[0].id == flow.BTN_SKIP


@pytest.mark.asyncio
async def test_not_my_message_when_idle() -> None:
    ctx = _ctx()
    assert (await _say(ctx, "सब ठीक है")).handled is False
    assert ctx.class_stage == flow.STAGE_NONE


@pytest.mark.asyncio
async def test_words_then_yes_saves_in_order() -> None:
    ctx = _ctx()
    await _say(ctx, "my class")
    asked = await _say(ctx, "बच्चे हासिल भूल जाते हैं और गिनती में गलती करते हैं")
    assert ctx.class_stage == flow.STAGE_CONFIRM
    assert asked.messages[0].buttons[0].id == "btn_yes"
    saved = await _say(ctx, "", "btn_yes")
    assert saved.saved and ctx.class_stage == flow.STAGE_NONE
    assert set(ctx.class_struggles) == {"NUM_ADD_CARRY", "NUM_COUNTING"}
    body = saved.messages[0].text_hi or ""
    assert "पुस्तिका का सुझाव" in body and saved.messages[0].citations


@pytest.mark.asyncio
async def test_no_goes_back_to_asking_without_saving() -> None:
    ctx = _ctx()
    await _say(ctx, "मेरी कक्षा")
    await _say(ctx, "घटाव")
    res = await _say(ctx, "", "btn_no")
    assert ctx.class_stage == flow.STAGE_ASKING and not res.saved
    assert ctx.class_struggles == []


@pytest.mark.asyncio
async def test_number_replies_pick_chips_and_cap_at_three() -> None:
    ctx = _ctx()
    await _say(ctx, "मेरी कक्षा")
    await _say(ctx, "१, ३ और 2 और 5")
    assert ctx.class_pending == [LIB.chips()[i].id for i in (0, 2, 1)]
    assert len(ctx.class_pending) == settings.STRUGGLE_MAX_CHOSEN
    await _say(ctx, "yes")
    assert ctx.class_struggles == [LIB.chips()[i].id for i in (0, 2, 1)]


@pytest.mark.asyncio
async def test_something_else_stores_nothing_and_says_there_is_no_practice_case() -> None:
    ctx = _ctx()
    await _say(ctx, "मेरी कक्षा")
    res = await _say(ctx, str(len(LIB.chips()) + 1))
    assert ctx.class_struggles == [] and ctx.class_stage == flow.STAGE_ASKING
    assert "अभ्यास का केस नहीं" in (res.messages[0].text_hi or "")
    assert res.messages[0].citations
    unmatched = await _say(ctx, "मौसम बहुत अच्छा है")
    assert "कुछ दर्ज नहीं किया" in (unmatched.messages[0].text_hi or "")
    assert ctx.class_struggles == []


@pytest.mark.asyncio
async def test_skip_button_ends_the_question() -> None:
    ctx = _ctx()
    await _say(ctx, "मेरी कक्षा")
    res = await _say(ctx, "", flow.BTN_SKIP)
    assert ctx.class_stage == flow.STAGE_NONE and res.handled and not res.saved


@pytest.mark.asyncio
async def test_a_known_command_leaves_the_question_and_is_not_swallowed() -> None:
    ctx = _ctx()
    await _say(ctx, "मेरी कक्षा")
    res = await _say(ctx, "help")
    assert res.handled is False and ctx.class_stage == flow.STAGE_NONE


@pytest.mark.asyncio
async def test_invite_has_two_buttons_and_start_opens_the_question() -> None:
    msg = flow.invite_message()
    assert [b.id for b in msg.buttons] == [flow.BTN_START, flow.BTN_SKIP]
    ctx = _ctx()
    res = await _say(ctx, "", flow.BTN_START)
    assert ctx.class_stage == flow.STAGE_ASKING and res.handled


def test_clean_ids_filters_dedups_and_caps() -> None:
    assert flow.clean_ids(["X", IDS[0], IDS[0], IDS[1], IDS[2], IDS[3]]) == IDS[:3]


def test_number_parser_only_claims_number_replies() -> None:
    assert flow.parse_number_choice("हासिल") is None
    assert flow.parse_number_choice("2") == [LIB.chips()[1].id]
    assert flow.parse_number_choice("99") == []
    assert intent_of("2") != Intent.DELETE


def intent_of(text: str) -> Intent | None:
    return match_intent(text=text)
