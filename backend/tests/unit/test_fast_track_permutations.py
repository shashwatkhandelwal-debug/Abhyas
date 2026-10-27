"""Regression tests for Evaluator Fast-Track permutations on fallback tagger.

Tests all 3 order permutations and repeat clicks:
1. Permutation 1: A1 -> A2 -> B -> C
2. Permutation 2: A2 -> B -> A1 -> C
3. Permutation 3: B -> A2 -> A1 -> C
4. Repeats: A1 -> A1, A2 -> A2, B -> B
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.rehearsal.scene_runner import SceneRunner, load_personas
from backend.app.rehearsal.scene_store import SceneStore
from backend.app.rule_engine.child_state import ChildState
from backend.app.rule_engine.domain import (
    ChildRuntime,
    Problem,
    TeachingAct,
)
from backend.app.speech.tts import MockTTS


def _create_runner() -> SceneRunner:
    store = SceneStore()
    mock_tts = MockTTS()
    personas = load_personas()
    return SceneRunner(tts_provider=mock_tts, store=store, personas=personas)


async def _init_ravi_scene(runner: SceneRunner, a: int = 43, b: int = 27) -> UUID:
    teacher_id = uuid4()
    item = Problem(type="sub", a=a, b=b)
    ravi = ChildRuntime(
        persona_id="ravi",
        misconception="SUB_SMALLER_FROM_LARGER",
        temperament="confident",
        state=ChildState.CAN_EXPLAIN,
    )
    scene = await runner.create_scene(
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        item=item,
        children=[ravi],
    )
    return scene.scene_id


@pytest.mark.asyncio
async def test_fast_track_permutation_1_a1_a2_b() -> None:
    """Permutation 1: A1 (Tell Answer) -> A2 (New Problem) -> B (Scaffolding)."""
    runner = _create_runner()
    scene_id = await _init_ravi_scene(runner, 43, 27)

    # Turn 1: Chip A1 ("रवि, सही उत्तर 16 है")
    t1 = await runner.turn(scene_id=scene_id, transcript="रवि, सही उत्तर 16 है")
    assert TeachingAct.TELL_ANSWER.value in t1.turn.acts
    s1 = await runner.store.get(scene_id)
    assert s1 is not None and s1.scene_state.current_item.key() == "sub:43-27"
    assert s1.scene_state.children[0].state == ChildState.CAN_EXPLAIN
    assert any("16" in line.line_hi for line in t1.turn.child_lines)

    # Turn 2: Chip A2 ("अब 61 में से 28 घटाओ")
    t2 = await runner.turn(scene_id=scene_id, transcript="अब 61 में से 28 घटाओ")
    assert TeachingAct.GIVE_NEW_PROBLEM.value in t2.turn.acts
    s2 = await runner.store.get(scene_id)
    assert s2 is not None and s2.scene_state.current_item.key() == "sub:61-28"
    assert any("47" in line.line_hi for line in t2.turn.child_lines)

    # Turn 3: Chip B (Bundles & sticks scaffolding restoring 43-27)
    t3 = await runner.turn(
        scene_id=scene_id,
        transcript="चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।",
    )
    assert TeachingAct.CONCRETE_REPRESENTATION.value in t3.turn.acts
    s3 = await runner.store.get(scene_id)
    assert s3 is not None and s3.scene_state.current_item.key() == "sub:43-27"
    assert s3.scene_state.children[0].state == ChildState.PARTIAL
    assert any("16" in line.line_hi for line in t3.turn.child_lines)


@pytest.mark.asyncio
async def test_fast_track_permutation_2_a2_b_a1() -> None:
    """Permutation 2: A2 (New Problem) -> B (Scaffolding) -> A1 (Tell Answer)."""
    runner = _create_runner()
    scene_id = await _init_ravi_scene(runner, 43, 27)

    # Turn 1: Chip A2 ("अब 61 में से 28 घटाओ")
    t1 = await runner.turn(scene_id=scene_id, transcript="अब 61 में से 28 घटाओ")
    assert TeachingAct.GIVE_NEW_PROBLEM.value in t1.turn.acts
    s1 = await runner.store.get(scene_id)
    assert s1 is not None and s1.scene_state.current_item.key() == "sub:61-28"
    assert any("47" in line.line_hi for line in t1.turn.child_lines)

    # Turn 2: Chip B (Scaffolding on 43-27)
    t2 = await runner.turn(
        scene_id=scene_id,
        transcript="चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।",
    )
    assert TeachingAct.CONCRETE_REPRESENTATION.value in t2.turn.acts
    s2 = await runner.store.get(scene_id)
    assert s2 is not None and s2.scene_state.current_item.key() == "sub:43-27"
    assert s2.scene_state.children[0].state == ChildState.PARTIAL
    assert any("16" in line.line_hi for line in t2.turn.child_lines)

    # Turn 3: Chip A1 on active 43-27 ("रवि, सही उत्तर 16 है")
    t3 = await runner.turn(scene_id=scene_id, transcript="रवि, सही उत्तर 16 है")
    assert TeachingAct.TELL_ANSWER.value in t3.turn.acts
    s3 = await runner.store.get(scene_id)
    assert s3 is not None and s3.scene_state.current_item.key() == "sub:43-27"
    assert any("16" in line.line_hi for line in t3.turn.child_lines)


@pytest.mark.asyncio
async def test_fast_track_permutation_3_b_a2_a1() -> None:
    """Permutation 3: B (Scaffolding) -> A2 (New Problem) -> A1 (Dynamic Tell Answer)."""
    runner = _create_runner()
    scene_id = await _init_ravi_scene(runner, 43, 27)

    # Turn 1: Chip B (Scaffolding on 43-27)
    t1 = await runner.turn(
        scene_id=scene_id,
        transcript="चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।",
    )
    assert TeachingAct.CONCRETE_REPRESENTATION.value in t1.turn.acts
    s1 = await runner.store.get(scene_id)
    assert s1 is not None and s1.scene_state.current_item.key() == "sub:43-27"
    assert s1.scene_state.children[0].state == ChildState.PARTIAL
    assert any("16" in line.line_hi for line in t1.turn.child_lines)

    # Turn 2: Chip A2 ("अब 61 में से 28 घटाओ")
    t2 = await runner.turn(scene_id=scene_id, transcript="अब 61 में से 28 घटाओ")
    assert TeachingAct.GIVE_NEW_PROBLEM.value in t2.turn.acts
    s2 = await runner.store.get(scene_id)
    assert s2 is not None and s2.scene_state.current_item.key() == "sub:61-28"
    assert any("47" in line.line_hi for line in t2.turn.child_lines)

    # Turn 3: Chip A1 dynamically computed for current board 61-28 (61-28 = 33)
    t3 = await runner.turn(scene_id=scene_id, transcript="रवि, सही उत्तर 33 है")
    assert TeachingAct.TELL_ANSWER.value in t3.turn.acts
    s3 = await runner.store.get(scene_id)
    assert s3 is not None and s3.scene_state.current_item.key() == "sub:61-28"
    assert any("33" in line.line_hi for line in t3.turn.child_lines)


@pytest.mark.asyncio
async def test_fast_track_repeat_taps() -> None:
    """Repeat taps: A1->A1, A2->A2, B->B stay completely deterministic."""
    runner = _create_runner()
    scene_id = await _init_ravi_scene(runner, 43, 27)

    # Repeat A1
    r1 = await runner.turn(scene_id=scene_id, transcript="रवि, सही उत्तर 16 है")
    assert TeachingAct.TELL_ANSWER.value in r1.turn.acts
    r2 = await runner.turn(scene_id=scene_id, transcript="रवि, सही उत्तर 16 है")
    assert TeachingAct.TELL_ANSWER.value in r2.turn.acts
    s_r2 = await runner.store.get(scene_id)
    assert s_r2 is not None and s_r2.scene_state.current_item.key() == "sub:43-27"

    # Repeat A2
    r3 = await runner.turn(scene_id=scene_id, transcript="अब 61 में से 28 घटाओ")
    assert TeachingAct.GIVE_NEW_PROBLEM.value in r3.turn.acts
    r4 = await runner.turn(scene_id=scene_id, transcript="अब 61 में से 28 घटाओ")
    assert TeachingAct.GIVE_NEW_PROBLEM.value in r4.turn.acts
    s_r4 = await runner.store.get(scene_id)
    assert s_r4 is not None and s_r4.scene_state.current_item.key() == "sub:61-28"

    # Repeat B
    r5 = await runner.turn(
        scene_id=scene_id,
        transcript="चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।",
    )
    assert TeachingAct.CONCRETE_REPRESENTATION.value in r5.turn.acts
    r6 = await runner.turn(
        scene_id=scene_id,
        transcript="चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।",
    )
    assert TeachingAct.CONCRETE_REPRESENTATION.value in r6.turn.acts
    s_r6 = await runner.store.get(scene_id)
    assert s_r6 is not None and s_r6.scene_state.current_item.key() == "sub:43-27"
    assert s_r6.scene_state.children[0].state == ChildState.PARTIAL


def _chip_b_text(a: int, b: int) -> str:
    """Python twin of getChipBText() in chat.js (the Python and JS tests pin the same strings)."""
    return (
        f"चलो {a} में से {b} फिर से करते हैं: देखो, {a // 10} बंडल और {a % 10} खुली तीलियाँ हैं, "
        f"{a % 10} में से {b % 10} नहीं निकलतीं, तो एक बंडल खोलो।"
    )


@pytest.mark.asyncio
async def test_fast_track_a2_then_b_when_tagger_returns_no_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude path: the real tagger returns problem=None for chip B's text.

    Chip B is built from the board (61-28 after chip A2), so with problem=None the board stays
    on the problem the teacher line talks about, and Ravi works that same problem.
    """
    from backend.app.llm.roles import act_tagger
    from backend.app.llm.schemas import ActTaggerOutput
    from backend.app.rehearsal import scene_runner

    chip_b = _chip_b_text(61, 28)

    async def claude_like_tag_act(*args: object, **kwargs: object) -> ActTaggerOutput:
        out = await act_tagger.tag_act(*args, **kwargs)  # type: ignore[arg-type]
        return (
            out.model_copy(update={"problem": None}) if kwargs.get("transcript") == chip_b else out
        )

    monkeypatch.setattr(scene_runner, "tag_act", claude_like_tag_act)

    runner = _create_runner()
    scene_id = await _init_ravi_scene(runner, 43, 27)

    t1 = await runner.turn(scene_id=scene_id, transcript="अब 61 में से 28 घटाओ")
    assert TeachingAct.GIVE_NEW_PROBLEM.value in t1.turn.acts

    t2 = await runner.turn(scene_id=scene_id, transcript=chip_b)
    assert TeachingAct.CONCRETE_REPRESENTATION.value in t2.turn.acts
    s2 = await runner.store.get(scene_id)
    assert s2 is not None and s2.scene_state.current_item.key() == "sub:61-28"
    # teacher line and child line are about the same problem: 61-28 = 33, never 43-27 = 16
    assert "43" not in chip_b and "27" not in chip_b
    assert any("33" in line.line_hi for line in t2.turn.child_lines)
    assert not any("16" in line.line_hi for line in t2.turn.child_lines)
