"""Unit tests for coach role and fallback scoring (spec/05 §5.6)."""

import unicodedata
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from backend.app.config import settings
from backend.app.content_models import MoveCard
from backend.app.db.models import ReviewItem
from backend.app.llm.client import LLMUnavailable
from backend.app.llm.guards import guard_coach
from backend.app.llm.roles.coach import (
    coach_feedback,
    create_coach_review_item,
    fallback_coach_feedback,
)
from backend.app.rule_engine.domain import TeachingAct


def _load_all_seed_moves() -> list[MoveCard]:
    """Loads all 4 seed moves from content/moves."""
    moves_dir = Path(__file__).resolve().parent.parent.parent.parent / "content" / "moves"
    moves: list[MoveCard] = []
    for p in sorted(moves_dir.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        moves.append(MoveCard.model_validate(data))
    return moves


def _load_move(move_id: str) -> MoveCard:
    """Loads a specific move by id."""
    moves_dir = Path(__file__).resolve().parent.parent.parent.parent / "content" / "moves"
    file_path = moves_dir / f"{move_id}.yaml"
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return MoveCard.model_validate(data)


# ── 1. Fallback Validity on All Seed Moves ────────────────────────────────────


def test_fallback_all_seed_moves_pass_guard() -> None:
    """Verifies deterministic fallback produces valid feedback passing guard_coach for every seed move."""
    seed_moves = _load_all_seed_moves()
    assert len(seed_moves) >= 4

    for move in seed_moves:
        rubric_ids = [c.id for c in move.rubric.criteria]

        # Case A: Minimal teacher transcript
        transcript_minimal = "टीचर: बच्चों, आज हम एक नया सवाल करेंगे। ध्यान से सुनो।"
        fb_min = fallback_coach_feedback(move=move, transcript=transcript_minimal)

        assert fb_min.confidence == 0.3
        assert fb_min.needs_review is True
        assert set(fb_min.scores.keys()) == set(rubric_ids)
        for s in fb_min.scores.values():
            assert s in (0, 1, 2)

        valid_min, msg_min = guard_coach(
            output=fb_min,
            rubric_criterion_ids=rubric_ids,
            teacher_transcript=transcript_minimal,
            rubric_rewards_not_telling=True,
            current_item_answer=None,
        )
        assert valid_min is True, f"Minimal fallback failed for {move.id}: {msg_min}"

        # Case B: Rich transcript with model rehearsal teacher lines
        teacher_lines = [
            f"टीचर: {t.text_hi}" for t in move.model_rehearsal if t.speaker == "teacher"
        ]
        transcript_rich = "\n".join(teacher_lines) if teacher_lines else transcript_minimal

        fb_rich = fallback_coach_feedback(
            move=move,
            transcript=transcript_rich,
            child_trajectories={"ravi": [0, 1]},
        )
        assert fb_rich.confidence == 0.3
        assert fb_rich.needs_review is True

        valid_rich, msg_rich = guard_coach(
            output=fb_rich,
            rubric_criterion_ids=rubric_ids,
            teacher_transcript=transcript_rich,
            rubric_rewards_not_telling=True,
            current_item_answer=None,
        )
        assert valid_rich is True, f"Rich fallback failed for {move.id}: {msg_rich}"


# ── 2. Scoring Logic & Trajectories ──────────────────────────────────────────


def test_fallback_signal_acts_scoring_with_trajectories() -> None:
    """Tests score 2 when child advanced, 1 when not advanced, and 0 when signal absent."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    rubric_ids = [c.id for c in move.rubric.criteria]

    transcript = (
        "टीचर: रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।\n"
        "रवि: 24 आया!\n"
        "टीचर: 4 बंडल और 3 तीलियाँ लो। तीलियाँ गिनकर बताओ।"
    )
    act_tags = [
        [TeachingAct.ASK_TO_EXPLAIN],
        [TeachingAct.CONCRETE_REPRESENTATION],
    ]

    # Child advanced -> score 2 on signal criteria
    fb_adv = fallback_coach_feedback(
        move=move,
        transcript=transcript,
        act_tags=act_tags,
        child_trajectories={"ravi": [0, 1]},
    )
    assert fb_adv.scores["crit_explain"] == 2
    assert fb_adv.evidence["crit_explain"] != ""
    assert "कैसे" in fb_adv.evidence["crit_explain"]

    assert fb_adv.scores["crit_concrete"] == 2
    assert fb_adv.evidence["crit_concrete"] != ""
    assert "बंडल" in fb_adv.evidence["crit_concrete"]

    # Child did not advance -> score 1
    fb_no_adv = fallback_coach_feedback(
        move=move,
        transcript=transcript,
        act_tags=act_tags,
        child_trajectories={"ravi": [0, 0]},
    )
    assert fb_no_adv.scores["crit_explain"] == 1
    assert fb_no_adv.scores["crit_concrete"] == 1

    # Absent signal act -> score 0 and evidence empty
    assert fb_no_adv.scores["crit_all_children"] == 0
    assert fb_no_adv.evidence["crit_all_children"] == ""

    valid, msg = guard_coach(fb_adv, rubric_ids, transcript, True, 16)
    assert valid is True, msg


def test_fallback_negative_act_forces_score_zero() -> None:
    """Negative act (tell_answer) forces score 0 on crit_no_telling."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: सही उत्तर 16 है, लिख लो।"
    act_tags = [[TeachingAct.TELL_ANSWER]]

    fb = fallback_coach_feedback(
        move=move,
        transcript=transcript,
        act_tags=act_tags,
        child_trajectories={"ravi": [0, 1]},
        current_item_answer=16,
    )
    assert fb.scores["crit_no_telling"] == 0
    assert fb.evidence["crit_no_telling"] == ""


# ── 3. Word Budget & Respectful Register ─────────────────────────────────────


def test_fallback_word_budget_and_register_all_moves() -> None:
    """Verifies <= 60 words and respectful आप/आपने register on all seed moves."""
    seed_moves = _load_all_seed_moves()
    for move in seed_moves:
        fb = fallback_coach_feedback(move=move, transcript="टीचर: बताओ कैसे किया?")
        words_count = (
            len(fb.strength_hi.split()) + len(fb.change_hi.split()) + len(fb.exact_words_hi.split())
        )
        assert words_count <= settings.MAX_COACH_FEEDBACK_WORDS

        # Respectful register in strength + change
        evaluation_text = f"{fb.strength_hi} {fb.change_hi}"
        norm_tokens = set(unicodedata.normalize("NFC", evaluation_text).split())
        assert any(t in norm_tokens for t in ["आप", "आपने", "आपकी", "आपको"])
        assert "तुम" not in norm_tokens
        assert "तुमने" not in norm_tokens

        # All text NFC normalized
        for text in [fb.strength_hi, fb.change_hi, fb.exact_words_hi]:
            assert text == unicodedata.normalize("NFC", text)


# ── 4. Answer Leak Sanitization ──────────────────────────────────────────────


def test_fallback_prevents_answer_leak_for_num_sub() -> None:
    """In NUM_SUB_REGROUP_BUNDLES, crit_no_telling feedback bank mentions 16. Fallback sanitizes it."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि, 43 में से 27 घटाकर दिखाओ।"

    fb = fallback_coach_feedback(
        move=move,
        transcript=transcript,
        current_item_answer=16,
    )

    # 16 must NOT be in exact_words_hi
    assert "16" not in fb.exact_words_hi

    # Guard check must pass with rubric_rewards_not_telling=True and current_item_answer=16
    rubric_ids = [c.id for c in move.rubric.criteria]
    valid, msg = guard_coach(fb, rubric_ids, transcript, True, 16)
    assert valid is True, msg


# ── 5. Single Sentence Checks ────────────────────────────────────────────────


def test_fallback_single_sentences() -> None:
    """Each feedback sentence must have <= 1 internal terminator."""
    seed_moves = _load_all_seed_moves()
    for move in seed_moves:
        fb = fallback_coach_feedback(move=move, transcript="टीचर: अच्छा सोचा तुमने।")
        for field, text in [
            ("strength", fb.strength_hi),
            ("change", fb.change_hi),
            ("exact_words", fb.exact_words_hi),
        ]:
            stripped = text.strip().rstrip("।,.!? ")
            import re

            inner_terminators = len(re.findall(r"[।\.]", stripped))
            assert inner_terminators <= 1, (
                f"{field} in {move.id} has {inner_terminators} internal stops: {text}"
            )


# ── 6. Retry & Improvement Tracking ──────────────────────────────────────────


def test_fallback_retry_improvement_flag() -> None:
    """improved_since_last is set when attempt > 1 and teacher achieved scores > 0."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि, तुमने कैसे किया? बताओ।"
    act_tags = [[TeachingAct.ASK_TO_EXPLAIN]]

    # First attempt: improved_since_last is False
    fb1 = fallback_coach_feedback(move=move, transcript=transcript, attempt=1)
    assert fb1.improved_since_last is False

    # Second attempt with improvement: improved_since_last is True
    fb2 = fallback_coach_feedback(
        move=move,
        transcript=transcript,
        act_tags=act_tags,
        attempt=2,
        previous_change_hi="बच्चे से उसका तरीका पूछिए।",
    )
    assert fb2.improved_since_last is True

    # Second attempt with 0 scores: improved_since_last is False
    fb_zero = fallback_coach_feedback(
        move=move,
        transcript="टीचर: कुछ नहीं।",
        act_tags=[],
        attempt=2,
        previous_change_hi="बच्चे से उसका तरीका पूछिए।",
    )
    assert fb_zero.improved_since_last is False


# ── 7. Async Role Runner (coach_feedback) ────────────────────────────────────


@pytest.mark.asyncio
async def test_coach_feedback_success_high_confidence() -> None:
    """Successful LLM call with confidence >= 0.60 returns valid output without review flag."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।"

    mock_output: dict[str, Any] = {
        "scores": {
            "crit_explain": 2,
            "crit_concrete": 0,
            "crit_no_telling": 0,
            "crit_all_children": 0,
        },
        "evidence": {
            "crit_explain": "तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।",
            "crit_concrete": "",
            "crit_no_telling": "",
            "crit_all_children": "",
        },
        "strength_hi": "आपने बच्चे से उसका तरीका पूछा, जिससे उसकी सोच स्पष्ट हुई।",
        "change_hi": "अगली बार बंडल और खुली तीलियों का उपयोग करके घटाव करवाइए।",
        "exact_words_hi": "रवि, 4 बंडल और 3 तीलियाँ लो। अब 7 तीलियाँ हटाओ।",
        "improved_since_last": False,
        "confidence": 0.88,
    }

    with patch("backend.app.llm.roles.coach.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_output
        fb = await coach_feedback(move=move, transcript=transcript)

        assert fb.confidence == 0.88
        assert fb.needs_review is False
        assert fb.scores["crit_explain"] == 2
        mock_call.assert_called_once()


@pytest.mark.asyncio
async def test_coach_feedback_low_confidence_flags_review() -> None:
    """Confidence < 0.60 sets needs_review=True and instantiates ReviewItem."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।"

    mock_output: dict[str, Any] = {
        "scores": {
            "crit_explain": 1,
            "crit_concrete": 0,
            "crit_no_telling": 0,
            "crit_all_children": 0,
        },
        "evidence": {
            "crit_explain": "तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।",
            "crit_concrete": "",
            "crit_no_telling": "",
            "crit_all_children": "",
        },
        "strength_hi": "आपने बच्चे से उसका तरीका पूछा, जिससे उसकी सोच स्पष्ट हुई।",
        "change_hi": "अगली बार बंडल और खुली तीलियों का उपयोग करके घटाव करवाइए।",
        "exact_words_hi": "रवि, 4 बंडल और 3 तीलियाँ लो। अब 7 तीलियाँ हटाओ।",
        "improved_since_last": False,
        "confidence": 0.52,  # < 0.60 threshold
    }

    mock_db = MagicMock()
    with patch("backend.app.llm.roles.coach.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_output
        fb = await coach_feedback(move=move, transcript=transcript, ref_id="scene-123", db=mock_db)

        assert fb.confidence == 0.52
        assert fb.needs_review is True
        mock_db.add.assert_called_once()
        added_item = mock_db.add.call_args[0][0]
        assert isinstance(added_item, ReviewItem)
        assert added_item.kind == "rehearsal_score"
        assert added_item.ref_id == "scene-123"


@pytest.mark.asyncio
async def test_coach_feedback_retry_on_guard_failure() -> None:
    """When attempt 1 fails guard (e.g. disrespectful register 'तुमने'), retries and succeeds."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।"

    invalid_output: dict[str, Any] = {
        "scores": {
            "crit_explain": 2,
            "crit_concrete": 0,
            "crit_no_telling": 0,
            "crit_all_children": 0,
        },
        "evidence": {
            "crit_explain": "तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।",
            "crit_concrete": "",
            "crit_no_telling": "",
            "crit_all_children": "",
        },
        "strength_hi": "तुमने बच्चे से बहुत अच्छा पूछा।",  # Disrespectful तुम/तुमने
        "change_hi": "अगली बार बंडल लाओ।",
        "exact_words_hi": "रवि, 4 बंडल लो।",
        "improved_since_last": False,
        "confidence": 0.85,
    }

    valid_output: dict[str, Any] = {
        "scores": {
            "crit_explain": 2,
            "crit_concrete": 0,
            "crit_no_telling": 0,
            "crit_all_children": 0,
        },
        "evidence": {
            "crit_explain": "तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।",
            "crit_concrete": "",
            "crit_no_telling": "",
            "crit_all_children": "",
        },
        "strength_hi": "आपने बच्चे से उसका तरीका पूछा, जिससे उसकी सोच स्पष्ट हुई।",
        "change_hi": "अगली बार बंडल और खुली तीलियों का उपयोग करके घटाव करवाइए।",
        "exact_words_hi": "रवि, 4 बंडल और 3 तीलियाँ लो। अब 7 तीलियाँ हटाओ।",
        "improved_since_last": False,
        "confidence": 0.85,
    }

    with patch("backend.app.llm.roles.coach.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [invalid_output, valid_output]
        fb = await coach_feedback(move=move, transcript=transcript)

        assert mock_call.call_count == 2
        assert fb.confidence == 0.85
        assert fb.needs_review is False
        assert "आपने" in fb.strength_hi


@pytest.mark.asyncio
async def test_coach_feedback_fallback_on_double_failure() -> None:
    """When both LLM attempts fail guard checks, falls back to deterministic coach."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि, तुमने 43 में से 27 कैसे घटाया? मुझे समझाओ।"

    invalid_output: dict[str, Any] = {
        "scores": {"bad_key": 2},
        "evidence": {"bad_key": "x"},
        "strength_hi": "आपने अच्छा किया।",
        "change_hi": "अगली बार सुधारें।",
        "exact_words_hi": "रवि, तीली लो।",
        "confidence": 0.9,
    }

    with patch("backend.app.llm.roles.coach.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [invalid_output, invalid_output]
        fb = await coach_feedback(move=move, transcript=transcript)

        assert mock_call.call_count == 2
        assert fb.confidence == 0.3
        assert fb.needs_review is True
        assert set(fb.scores.keys()) == {c.id for c in move.rubric.criteria}


@pytest.mark.asyncio
async def test_coach_feedback_fallback_on_llm_exception() -> None:
    """When LLM call raises LLMUnavailable, falls back immediately."""
    move = _load_move("NUM_SUB_REGROUP_BUNDLES")
    transcript = "टीचर: रवि बताओ।"

    with patch("backend.app.llm.roles.coach.call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = LLMUnavailable("Anthropic API error")
        fb = await coach_feedback(move=move, transcript=transcript)

        assert fb.confidence == 0.3
        assert fb.needs_review is True


# ── 8. Transcript Formats Support ────────────────────────────────────────────


def test_fallback_handles_various_transcript_formats() -> None:
    """Ensures fallback works with string, list of strings, and list of dicts."""
    move = _load_move("NUM_ADD_CARRY_BUNDLES")

    # Format 1: Multi-line string
    trans_str = "टीचर: रवि, तुमने कैसे जोड़ा?\nरवि: 73!\nटीचर: तीलियाँ गिनकर देखो।"
    fb1 = fallback_coach_feedback(move=move, transcript=trans_str)
    assert fb1.scores["crit_explain"] > 0

    # Format 2: List of strings
    trans_list = [
        "टीचर: रवि, तुमने कैसे जोड़ा?",
        "रवि: 73!",
        "टीचर: तीलियाँ गिनकर देखो।",
    ]
    fb2 = fallback_coach_feedback(move=move, transcript=trans_list)
    assert fb2.scores["crit_explain"] > 0

    # Format 3: List of turn dicts
    trans_dicts: list[dict[str, Any]] = [
        {"speaker": "teacher", "text_hi": "रवि, तुमने कैसे जोड़ा?"},
        {"speaker": "ravi", "text_hi": "73!"},
        {"speaker": "teacher", "text_hi": "तीलियाँ गिनकर देखो।"},
    ]
    fb3 = fallback_coach_feedback(move=move, transcript=trans_dicts)
    assert fb3.scores["crit_explain"] > 0


# ── 9. ReviewItem Creation Helper ────────────────────────────────────────────


def test_create_coach_review_item() -> None:
    """Tests creation of ReviewItem entity."""
    mock_db = MagicMock()
    item = create_coach_review_item(
        ref_id="rehearsal-001",
        confidence=0.45,
        db=mock_db,
    )
    assert item.kind == "rehearsal_score"
    assert item.ref_id == "rehearsal-001"
    assert item.status == "open"
    assert "0.45" in (item.reason or "")
    mock_db.add.assert_called_once_with(item)
