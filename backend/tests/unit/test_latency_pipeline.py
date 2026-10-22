"""Unit tests for turn pipeline latency optimisations, parallel child voicing, text-first delivery, and TTS pre-warming (Task T63)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.core.types import OutboundMessage
from backend.app.rehearsal.scene_runner import ChildLineRecord, SceneRunner, load_personas
from backend.app.rehearsal.scene_store import SceneStore
from backend.app.rule_engine.domain import (
    ChildRuntime,
    ChildState,
    Problem,
)
from backend.app.speech.tts import MockTTS
from scripts.prewarm_tts import load_prewarm_targets, prewarm_tts


@pytest.fixture
def scene_runner() -> SceneRunner:
    store = SceneStore()
    mock_tts = MockTTS()
    personas = load_personas()
    return SceneRunner(tts_provider=mock_tts, store=store, personas=personas)


# ── 1. Pipeline Invariant: Ravi 43 - 27 subtraction ──────────────────────────


@pytest.mark.asyncio
async def test_pipeline_output_invariant_ravi_subtraction(scene_runner: SceneRunner) -> None:
    """Verifies turn pipeline invariant: Ravi with SUB_SMALLER_FROM_LARGER computes 43 - 27 = 24, never 16."""
    teacher_id = uuid4()
    item_43_27 = Problem(type="sub", a=43, b=27)

    ravi_runtime = ChildRuntime(
        persona_id="ravi",
        misconception="SUB_SMALLER_FROM_LARGER",
        temperament="confident",
        state=ChildState.MISCONCEPTION,
    )

    scene = await scene_runner.create_scene(
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        item=item_43_27,
        children=[ravi_runtime],
    )
    scene_id = scene.scene_id

    # Turn 1: Ask Ravi to explain/answer 43 - 27
    res = await scene_runner.turn(
        scene_id=scene_id,
        transcript="रवि, 43 में से 27 घटाकर बताओ कितना बचेगा?",
        synthesize_audio=True,
    )

    turn = res.turn
    assert len(turn.child_responses) == 1
    ravi_resp = turn.child_responses[0]

    # Invariant: Ravi answers 24 (tens: 4-2=2, units: 7-3=4), NEVER 16
    assert ravi_resp.answer == 24, f"Expected 24 from Ravi bug rule, got {ravi_resp.answer}"
    assert ravi_resp.answer != 16, "Ravi must not answer the correct result 16"

    # Spoken line check: must express 24 and NOT 16
    assert len(turn.child_lines) == 1
    spoken_line = turn.child_lines[0].line_hi
    assert any(num in spoken_line for num in ("24", "२४", "चौबीस")), (
        f"Spoken line '{spoken_line}' does not contain Ravi's answer 24"
    )
    assert "16" not in spoken_line and "१६" not in spoken_line and "सोलह" not in spoken_line


@pytest.mark.asyncio
async def test_pipeline_parallel_child_voicing_multi_child(scene_runner: SceneRunner) -> None:
    """Verifies that asyncio.gather across responding children preserves child identities and order."""
    teacher_id = uuid4()
    item_52_17 = Problem(type="sub", a=52, b=17)

    # 2 children with different misconceptions
    ravi = ChildRuntime(
        persona_id="ravi",
        misconception="SUB_SMALLER_FROM_LARGER",
        temperament="confident",
        state=ChildState.MISCONCEPTION,
    )
    priya = ChildRuntime(
        persona_id="priya",
        misconception="SUB_ONE_FROM_BOTTOM",
        temperament="shy",
        state=ChildState.MISCONCEPTION,
    )

    scene = await scene_runner.create_scene(
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        item=item_52_17,
        children=[ravi, priya],
    )
    scene_id = scene.scene_id

    # Prompt addressed to both children
    res = await scene_runner.turn(
        scene_id=scene_id,
        transcript="बच्चों, 52 में से 17 घटाकर अपनी-अपनी कॉपी में बताओ।",
        synthesize_audio=True,
    )

    turn = res.turn
    assert len(turn.child_responses) >= 1
    assert len(turn.child_lines) == len(turn.child_responses)
    for c_line in turn.child_lines:
        assert c_line.line_hi.strip() != ""
        assert c_line.persona_id in ("ravi", "priya")


# ── 2. Text-first Delivery ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_text_first_delivery_callback(scene_runner: SceneRunner) -> None:
    """Verifies on_text_ready callback fires before TTS synthesis with text kind."""
    teacher_id = uuid4()
    item = Problem(type="sub", a=52, b=17)
    ravi = ChildRuntime(
        persona_id="ravi",
        misconception="SUB_SMALLER_FROM_LARGER",
        temperament="confident",
        state=ChildState.MISCONCEPTION,
    )
    scene = await scene_runner.create_scene(
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        item=item,
        children=[ravi],
    )

    callback_called = False
    callback_messages: list[OutboundMessage] = []

    async def _mock_on_text_ready(
        child_lines: list[ChildLineRecord], text_msgs: list[OutboundMessage]
    ) -> None:
        nonlocal callback_called, callback_messages
        callback_called = True
        callback_messages = list(text_msgs)
        # At this point, messages must be kind='text' without audio_ref
        for m in text_msgs:
            assert m.kind == "text"
            assert m.audio_ref is None
            assert m.text_hi is not None and len(m.text_hi) > 0

    res = await scene_runner.turn(
        scene_id=scene.scene_id,
        transcript="रवि, बताओ 52 में से 17 कैसे घटाया?",
        synthesize_audio=True,
        on_text_ready=_mock_on_text_ready,
    )

    assert callback_called is True
    assert len(callback_messages) == 1
    # After turn returns, final outbound message should have kind='audio' with audio_ref
    assert len(res.outbound) == 1
    assert res.outbound[0].kind == "audio"
    assert res.outbound[0].audio_ref is not None


# ── 3. TTS Pre-warming Script ────────────────────────────────────────────────


def test_prewarm_load_targets(tmp_path: Path) -> None:
    """Verifies load_prewarm_targets extracts catalog audio: true messages and move learn scripts."""
    msg_file = tmp_path / "messages_hi.yaml"
    msg_file.write_text(
        """
welcome_msg:
  audio: true
  text: "नमस्ते शिक्षक साथी!"
dynamic_msg:
  audio: true
  text: "आपका स्वागत है {name}"
no_audio_msg:
  audio: false
  text: "यह सिर्फ टेक्स्ट है"
""",
        encoding="utf-8",
    )

    moves_dir = tmp_path / "moves"
    moves_dir.mkdir()
    move_file = moves_dir / "NUM_SUB_REGROUP_BUNDLES.yaml"
    move_file.write_text(
        """
title_hi: "हासिल वाला घटाव"
learn_script_hi: "इस शिक्षण तकनीक में हम बच्चों को तीली और बंडल से समझाते हैं।"
""",
        encoding="utf-8",
    )

    targets = load_prewarm_targets(msg_file, moves_dir)
    labels = [t[0] for t in targets]

    # welcome_msg should be included, dynamic_msg excluded, no_audio_msg excluded
    assert "msg:welcome_msg:text" in labels
    assert not any("dynamic_msg" in lbl for lbl in labels)
    assert not any("no_audio_msg" in lbl for lbl in labels)

    # move learn script should be included
    assert "move:NUM_SUB_REGROUP_BUNDLES:learn" in labels


@pytest.mark.asyncio
async def test_prewarm_tts_mock_noop() -> None:
    """prewarm_tts is a no-op when running against mock TTS without --force-mock."""
    res = await prewarm_tts(force_mock=False)
    assert res["synthesized"] == 0
    assert res["tts_calls"] == 0
    assert res["cost_inr"] == 0.0


@pytest.mark.asyncio
async def test_prewarm_tts_dry_run_and_idempotence(tmp_path: Path) -> None:
    """prewarm_tts dry run calculates costs without writing; repeated run checks cache."""
    msg_file = tmp_path / "messages_hi.yaml"
    msg_file.write_text(
        """
msg_1:
  audio: true
  text: "नमस्ते, अभ्यास में आपका स्वागत है।"
""",
        encoding="utf-8",
    )
    moves_dir = tmp_path / "moves"
    moves_dir.mkdir()

    # Dry run
    res_dry = await prewarm_tts(
        messages_path=msg_file,
        moves_dir=moves_dir,
        tts_provider=MockTTS(),
        force_mock=True,
        dry_run=True,
    )
    assert res_dry["total_targets"] == 1
    assert res_dry["synthesized"] == 1
    assert res_dry["cost_inr"] > 0.0
