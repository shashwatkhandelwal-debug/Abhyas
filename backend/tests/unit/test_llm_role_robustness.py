"""Regression tests for the production LLM-role failures (truncated tool input, word-count
guard discard, off-topic replacing a correction) and the per-role INFO log line."""

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from anthropic.types import Message, ToolUseBlock, Usage

from backend.app.config import settings
from backend.app.content_models import PersonaCard
from backend.app.llm import client as llm_client
from backend.app.llm.client import budget_tracker, call_tool
from backend.app.llm.roles import act_tagger as act_tagger_mod
from backend.app.llm.roles import child_voice as child_voice_mod
from backend.app.llm.roles.child_voice import truncate_at_sentence_boundary, voice_child_line
from backend.app.llm.schemas import ActTaggerOutput, ChildVoiceOutput
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    ChildState,
    Domain,
    Problem,
    ResponseKind,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine


def _msg(tool_input: dict[str, Any], stop_reason: str = "tool_use") -> Message:
    return Message(
        id="msg_x",
        type="message",
        role="assistant",
        content=[ToolUseBlock(type="tool_use", id="t1", name="tool", input=tool_input)],
        model="claude-haiku-5-5",
        stop_reason=stop_reason,  # type: ignore[arg-type]
        usage=Usage(input_tokens=10, output_tokens=5),
    )


async def _call(create: AsyncMock) -> dict[str, Any]:
    with (
        patch.object(settings, "LLM_PROVIDER", "anthropic"),
        patch.object(settings, "ANTHROPIC_API_KEY", "sk-ant-test"),
        patch("anthropic.AsyncAnthropic") as cls,
        patch.object(llm_client, "_anthropic_client", None),
    ):
        client = AsyncMock()
        client.messages.create = create
        cls.return_value = client
        budget_tracker.reset()
        try:
            return await call_tool(
                role="child_voice",
                model="claude-haiku-5-5",
                system="s",
                messages=[{"role": "user", "content": "hi"}],
                tool_name="tool",
                input_schema={"properties": {}},
                max_tokens=128,
            )
        finally:
            budget_tracker.reset()


# ── Part 1a: truncated replies surface as input={} and were passed on as if valid ──
@pytest.mark.asyncio
async def test_truncated_reply_is_retried_with_more_tokens_not_returned_empty() -> None:
    create = AsyncMock(side_effect=[_msg({}, "max_tokens"), _msg({"line_hi": "ठीक है!"})])
    result = await _call(create)
    assert result == {"line_hi": "ठीक है!"}
    assert create.call_count == 2
    assert create.call_args_list[1].kwargs["max_tokens"] == 256  # doubled from 128


@pytest.mark.asyncio
async def test_repeated_truncation_raises_instead_of_returning_empty_input() -> None:
    create = AsyncMock(side_effect=[_msg({}, "max_tokens"), _msg({}, "max_tokens")])
    with pytest.raises(llm_client.LLMUnavailable):
        await _call(create)


def test_role_token_budgets_fit_devanagari_lines() -> None:
    # ~4 tokens/word: 25 words + tool-call overhead measured at ~110 tokens in production.
    assert settings.CHILD_VOICE_MAX_TOKENS >= 256
    assert settings.ACT_TAGGER_MAX_TOKENS >= 384


# ── Part 1b: over-long lines are shortened, not discarded ──
def test_truncate_keeps_whole_sentences() -> None:
    line = (
        "दीदी, 6 में से 2 गया तो 4 बचा। 3 में से 1 गया तो 2 बचा। तो जवाब 26 है। अरे वो खिड़की में चिड़िया देखो!"
    )
    out = truncate_at_sentence_boundary(line, 20)
    assert out.endswith("बचा।") and "26" not in out
    assert len(out.split()) <= 20


def test_truncate_hard_cuts_a_single_long_sentence() -> None:
    out = truncate_at_sentence_boundary(" ".join(["शब्द"] * 40), 25)
    assert len(out.split()) <= 25
    assert out.endswith("…")


@pytest.fixture
def aman() -> PersonaCard:
    return PersonaCard(
        id="aman",
        name_hi="अमन",
        age=7,
        temperament="distracted",
        voice_id="child_aman",
        speech_style_hi="चंचल",
        off_topic_lines_hi=["दीदी, मेरी चप्पल टूट गई।"],
    )


def _parrot(answer: int = 16) -> ChildResponse:
    return ChildResponse(
        persona_id="aman",
        kind=ResponseKind.PARROT,
        answer=answer,
        correct_answer=answer,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="distracted",
        item=Problem(type="sub", a=32, b=16),
        allowed_numbers={1, 32, 16},
    )


LONG = "दीदी, सोलह… अरे वो खिड़की में चिड़िया बैठी है। मेरी पेंसिल कहाँ गई पता नहीं। " + "और " * 12


@pytest.mark.asyncio
async def test_child_voice_retry_feeds_back_word_limit(aman: PersonaCard) -> None:
    ok = "दीदी, सोलह!"
    calls: list[list[dict[str, Any]]] = []

    async def fake(**kw: Any) -> dict[str, Any]:
        calls.append(list(kw["messages"]))
        return {"line_hi": LONG if len(calls) == 1 else ok}

    with patch.object(child_voice_mod, "call_tool", fake):
        line = await voice_child_line(_parrot(), aman)
    assert line == ok
    feedback = calls[1][-1]["content"]
    assert "at most 25 words" in feedback and LONG[:20] in feedback


@pytest.mark.asyncio
async def test_child_voice_truncates_instead_of_template_when_still_too_long(
    aman: PersonaCard,
) -> None:
    too_long = "दीदी, सोलह है। अरे वो खिड़की में चिड़िया बैठी है। " + "और " * 25

    async def fake(**kw: Any) -> dict[str, Any]:
        return {"line_hi": too_long}

    with patch.object(child_voice_mod, "call_tool", fake):
        line = await voice_child_line(_parrot(), aman)
    assert line.startswith("दीदी, सोलह है।")
    assert len(line.split()) <= settings.MAX_CHILD_LINE_WORDS
    assert "16" not in line  # not the "16… ?" template: the model's own words were kept


@pytest.mark.asyncio
async def test_child_voice_empty_input_falls_back_to_template(aman: PersonaCard) -> None:
    async def fake(**kw: Any) -> dict[str, Any]:
        return {}  # what a truncated reply used to look like

    with patch.object(child_voice_mod, "call_tool", fake):
        line = await voice_child_line(_parrot(), aman)
    assert line == "16… ?"


# ── act_tagger: retry carries feedback ──
@pytest.mark.asyncio
async def test_act_tagger_retry_feeds_back_empty_acts() -> None:
    seen: list[list[dict[str, Any]]] = []
    transcript = "Aman, sahi answer 16 hai, yaad rakho."

    async def fake(**kw: Any) -> dict[str, Any]:
        seen.append(list(kw["messages"]))
        if len(seen) == 1:
            return {"acts": [], "addressed_child": "aman", "quote": ""}
        return {"acts": ["tell_answer"], "addressed_child": "aman", "quote": "sahi answer 16 hai"}

    with patch.object(act_tagger_mod, "call_tool", fake):
        out = await act_tagger_mod.tag_act(
            transcript, "m", "sub:32-16", "aman", ["ravi", "priya", "aman"]
        )
    assert out.acts == [TeachingAct.TELL_ANSWER]
    assert len(seen) == 2
    assert "At least one act" in seen[1][-1]["content"]
    assert ActTaggerOutput  # schema import is exercised above


# ── Part 1c: a correction is answered, distraction is rare ──
def _scene() -> SceneState:
    items = [Problem(type="sub", a=32, b=16)]
    return SceneState(
        move_id="NUM_SUB_REGROUP_BUNDLES",
        domain=Domain.NUMERACY,
        effective_acts=[TeachingAct.ASK_TO_EXPLAIN],
        target_causes=["SUB_WRITE_ZERO_WHEN_STUCK"],
        items=items,
        current_item=items[0],
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="aman",
                misconception="SUB_WRITE_ZERO_WHEN_STUCK",
                temperament="distracted",
                state=ChildState.MISCONCEPTION,
            ),
        ],
        max_turns=15,
    )


def test_correction_with_stray_off_task_tag_is_not_answered_with_distraction() -> None:
    # Haiku tagged "sahi answer 16 hai" as tell_answer AND off_task: the correction wins.
    res = RuleEngine.step(
        _scene(),
        TaggedTurn(acts=[TeachingAct.OFF_TASK, TeachingAct.TELL_ANSWER], addressed_child="aman"),
    )
    assert res.responses[0].persona_id == "aman"
    assert res.responses[0].kind == ResponseKind.PARROT


def test_off_topic_only_once_per_scene() -> None:
    scene = _scene()
    off = TaggedTurn(acts=[TeachingAct.OFF_TASK], addressed_child="aman")
    first = RuleEngine.step(scene, off)
    second = RuleEngine.step(scene, off)
    assert first.responses[0].kind == ResponseKind.OFF_TOPIC
    assert second.responses[0].kind != ResponseKind.OFF_TOPIC
    assert scene.distractions_used == 1


def test_interject_counts_against_the_same_budget() -> None:
    scene = _scene()
    ravi = TaggedTurn(acts=[TeachingAct.REPEAT_QUESTION], addressed_child="ravi")
    kinds = [r.kind for _ in range(8) for r in RuleEngine.step(scene, ravi).responses]
    assert kinds.count(ResponseKind.INTERJECT) == 1


# ── Part 1d: one INFO line per role call ──
@pytest.mark.asyncio
async def test_role_call_logs_role_model_latency_fallback(
    aman: PersonaCard, caplog: pytest.LogCaptureFixture
) -> None:
    async def ok(**kw: Any) -> dict[str, Any]:
        return ChildVoiceOutput(line_hi="दीदी, सोलह!").model_dump()

    async def broken(**kw: Any) -> dict[str, Any]:
        return {}

    with caplog.at_level(logging.INFO, logger="abhyas.llm.client"):
        with patch.object(child_voice_mod, "call_tool", ok):
            await voice_child_line(_parrot(), aman)
        with patch.object(child_voice_mod, "call_tool", broken):
            await voice_child_line(_parrot(), aman)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("llm_role")]
    assert len(lines) == 2
    assert f"role=child_voice model={settings.CLAUDE_MODEL_FAST} latency_ms=" in lines[0]
    assert lines[0].endswith("fallback_used=false")
    assert lines[1].endswith("fallback_used=true")
