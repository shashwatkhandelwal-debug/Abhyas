"""fix5 item 9 and 8: one language per coach feedback block; he/she for the simulated children."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from backend.app.content_models import Domain, MoveCard
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.pronouns import child_pronouns
from backend.app.llm.guards import guard_reply_language
from backend.app.llm.roles.coach import coach_feedback, fallback_coach_feedback
from backend.app.llm.schemas import SceneTurn
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildState,
    Problem,
    ResponseKind,
    TeachingAct,
)
from backend.app.sessions.outcome import outcome_line

MOVES_DIR = Path(__file__).resolve().parents[3] / "content" / "moves"
DEVA = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")


def _moves() -> list[MoveCard]:
    return [
        MoveCard.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(MOVES_DIR.glob("*.yaml"))
    ]


# ── the guard ────────────────────────────────────────────────────────────────


def test_guard_rejects_hindi_for_an_english_teacher_and_the_reverse() -> None:
    hindi = ["आपने बच्चे से उसका तरीका पूछा।", "अगली बार बंडल रखवाइए।", "रवि, तुमने कैसे किया?"]
    english = ["You asked the child how.", "Next time use bundles.", "Ravi, how did you do it?"]
    assert guard_reply_language(hindi, "hi")[0]
    assert guard_reply_language(english, "en")[0]
    assert not guard_reply_language(hindi, "en")[0]
    assert not guard_reply_language(english, "hi")[0]


def test_guard_ignores_the_teachers_own_quoted_words_and_a_letter_being_taught() -> None:
    assert guard_reply_language(["You said «तुमने कैसे किया» and the child answered well."], "en")[0]
    assert guard_reply_language(["Which matra is on म? Say it with the child, slowly."], "en")[0]
    assert guard_reply_language(["आपने ARP को बताया, यह बहुत अच्छा रहा।"], "hi")[0]


# ── the coach: language is passed in and enforced ────────────────────────────

_MOVE_ID = "NUM_SUB_REGROUP_BUNDLES"
_TURNS = [SceneTurn(speaker="teacher", text_hi="Ravi, how did you subtract 27 from 43?")]
_ACTS = [[TeachingAct.ASK_TO_EXPLAIN]]
_TRAJ = {"ravi": [ChildState.MISCONCEPTION, ChildState.CAN_EXPLAIN]}
_SCORES = {
    "crit_explain": 2,
    "crit_concrete": 0,
    "crit_no_telling": 0,
    "crit_all_children": 0,
}


def _tool_output(strength: str, change: str, words: str) -> dict[str, Any]:
    return {
        "scores": _SCORES,
        "evidence": {
            "crit_explain": "Ravi, how did you subtract 27 from 43?",
            "crit_concrete": "",
            "crit_no_telling": "",
            "crit_all_children": "",
        },
        "strength_hi": strength,
        "change_hi": change,
        "exact_words_hi": words,
        "improved_since_last": False,
        "confidence": 0.9,
    }


HINDI_OUT = _tool_output("आपने बच्चे से उसका तरीका पूछा।", "अगली बार बंडल रखवाइए।", "रवि, तुमने कैसे घटाया?")
ENGLISH_OUT = _tool_output(
    "You asked the child for the method.", "Next time use bundles.", "Ravi, how did you subtract?"
)


async def _run(lang: str, outputs: list[dict[str, Any]]) -> tuple[Any, AsyncMock]:
    move = next(m for m in _moves() if m.id == _MOVE_ID)
    with patch("backend.app.llm.roles.coach.call_tool", new_callable=AsyncMock) as call:
        call.side_effect = outputs
        res = await coach_feedback(
            move=move,
            turns=_TURNS,
            acts=_ACTS,
            trajectories=_TRAJ,
            target_child_id="ravi",
            current_item_answer=16,
            lang=lang,
        )
    return res, call


@pytest.mark.asyncio
async def test_prompt_carries_the_teachers_language() -> None:
    _, call = await _run("en", [ENGLISH_OUT])
    assert "entirely in English" in call.call_args[1]["system"]
    _, call = await _run("hi", [HINDI_OUT])
    assert "entirely in Hindi" in call.call_args[1]["system"]


@pytest.mark.asyncio
async def test_wrong_script_reply_is_retried_once_then_accepted_if_right() -> None:
    res, call = await _run("en", [HINDI_OUT, ENGLISH_OUT])
    assert call.call_count == 2
    assert not res.used_fallback
    assert not DEVA.search(res.feedback.strength_hi + res.feedback.exact_words_hi)


@pytest.mark.asyncio
@pytest.mark.parametrize(("lang", "bad"), [("en", HINDI_OUT), ("hi", ENGLISH_OUT)])
async def test_two_wrong_script_replies_fall_back_to_the_template_in_the_right_language(
    lang: str, bad: dict[str, Any]
) -> None:
    res, call = await _run(lang, [bad, bad])
    assert call.call_count == 2 and res.used_fallback
    f = res.feedback
    text = " ".join([f.strength_hi, f.change_hi, f.exact_words_hi])
    assert guard_reply_language([text], lang)[0]
    wrong = DEVA if lang == "en" else LATIN
    assert len(wrong.findall(text)) <= 0.15 * len(re.findall(r"[A-Za-zऀ-ॿ]", text))


# ── the template fallback, for every move, group and one-on-one, both languages ──


@pytest.mark.parametrize("move", _moves(), ids=lambda m: m.id)
@pytest.mark.parametrize("one_on_one", [False, True])
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_fallback_template_is_in_one_language(move: MoveCard, one_on_one: bool, lang: str) -> None:
    token = set_ui_lang(lang)
    try:
        fb = fallback_coach_feedback(
            move=move,
            turns=[SceneTurn(speaker="teacher", text_hi="ok")],
            acts=[[TeachingAct.REPEAT_QUESTION]],
            trajectories={"ravi": [ChildState.MISCONCEPTION]},
            target_child_id="ravi",
            current_item_answer=16,
            one_on_one=one_on_one,
        )
    finally:
        reset_ui_lang(token)
    ok, err = guard_reply_language([fb.strength_hi, fb.change_hi, fb.exact_words_hi], lang)
    assert ok, f"{move.id} {lang} one_on_one={one_on_one}: {err}"


def test_english_catalog_has_no_hindi_in_the_coach_lines() -> None:
    for key in ("coach_exact_words_contrast_math", "coach_exact_words_contrast_lit"):
        assert not DEVA.search(get_message(key, lang="en"))


# ── he / she for the children, four feedback templates, three children ───────

CHILDREN = [
    ("ravi", "he", "him", "his"),
    ("priya", "she", "her", "her"),
    ("aman", "he", "him", "his"),
]
OUTCOMES = [
    (ResponseKind.PARROT, Domain.NUMERACY, "coach_outcome_told"),
    (ResponseKind.RELAPSE, Domain.NUMERACY, "coach_outcome_relapse_scaffold"),
    (ResponseKind.SCAFFOLDED_CORRECT, Domain.LITERACY, "coach_outcome_concrete_literacy"),
    (ResponseKind.EXPLAIN_BUG, Domain.NUMERACY, "coach_outcome_explain"),
]


def _turn(persona: str, kind: ResponseKind) -> list[TurnRecord]:
    response = ChildResponse(
        persona_id=persona,
        kind=kind,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.PARTIAL,
        affect="neutral",
        item=Problem(type="sub", a=43, b=27),
    )
    return [TurnRecord(turn_index=1, transcript="x", acts=[], child_responses=[response])]


@pytest.mark.parametrize(("persona", "he", "him", "his"), CHILDREN)
@pytest.mark.parametrize(("kind", "domain", "key"), OUTCOMES)
def test_english_feedback_uses_the_childs_pronoun(
    persona: str, he: str, him: str, his: str, kind: ResponseKind, domain: Domain, key: str
) -> None:
    assert child_pronouns(persona) == {"he": he, "him": him, "his": his}
    token = set_ui_lang("en")
    try:
        line = outcome_line(_turn(persona, kind), "f", domain)
    finally:
        reset_ui_lang(token)
    assert line
    assert not re.search(r"\b(they|them|their)\b", line, re.IGNORECASE), line
    expected = get_message(
        key,
        lang="en",
        child=get_message(f"speaker_{persona}", lang="en"),
        **child_pronouns(persona),
    )
    assert line == expected


def test_the_literacy_line_reads_him_or_her_not_them() -> None:
    token = set_ui_lang("en")
    try:
        line = outcome_line(_turn("priya", ResponseKind.SCAFFOLDED_CORRECT), "f", Domain.LITERACY)
    finally:
        reset_ui_lang(token)
    assert "gave her something to hold on to" in line


def test_hindi_output_is_unchanged_by_the_pronoun_kwargs() -> None:
    token = set_ui_lang("hi")
    try:
        line = outcome_line(_turn("ravi", ResponseKind.PARROT), "f", Domain.NUMERACY)
    finally:
        reset_ui_lang(token)
    assert line and not re.search(r"[A-Za-z]{3,}", line)
