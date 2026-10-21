"""Integration tests for SceneRunner deliberate practice rehearsal (spec/02 §2.2, T19).

Runs the spec-mandated Ravi worked example end-to-end with MockLLM:
- Turn 1: ASK_TO_EXPLAIN -> Ravi EXPLAIN_BUG (answer 45, state CAN_EXPLAIN)
- Turn 2: CONCRETE_REPRESENTATION -> Ravi SCAFFOLDED_CORRECT (answer 35, state PARTIAL)
- Turn 3: CONTRAST_TWO_ANSWERS -> Ravi CORRECT_EXPLAINED (answer 35, state CORRECT)
Verifies stage timing metrics, child line guarding, and scene turn persistence.
"""

from uuid import uuid4

import pytest

from backend.app.rehearsal.scene_runner import SceneRunner, load_personas
from backend.app.rehearsal.scene_store import SceneStore
from backend.app.rule_engine.domain import (
    ChildRuntime,
    ChildState,
    Problem,
    ResponseKind,
)
from backend.app.speech.tts import MockTTS


@pytest.fixture
def scene_runner() -> SceneRunner:
    store = SceneStore()
    mock_tts = MockTTS()
    personas = load_personas()
    return SceneRunner(tts_provider=mock_tts, store=store, personas=personas)


@pytest.mark.asyncio
async def test_ravi_worked_example_end_to_end(scene_runner: SceneRunner) -> None:
    """Runs the spec-mandated Ravi worked example end-to-end on NUM_SUB_REGROUP_BUNDLES."""
    teacher_id = uuid4()
    item_52_17 = Problem(type="sub", a=52, b=17)

    # Setup single-child scene for Ravi (placement/focus worked example)
    ravi_runtime = ChildRuntime(
        persona_id="ravi",
        misconception="SUB_SMALLER_FROM_LARGER",
        temperament="confident",
        state=ChildState.MISCONCEPTION,
    )

    scene = await scene_runner.create_scene(
        teacher_id=teacher_id,
        move_id="NUM_SUB_REGROUP_BUNDLES",
        item=item_52_17,
        children=[ravi_runtime],
    )
    scene_id = scene.scene_id

    # ── Turn 1: ASK_TO_EXPLAIN ──────────────────────────────────────────
    t1_text = "रवि, 52 में से 17 कैसे घटाया? बताओ।"
    res1 = await scene_runner.turn(
        scene_id=scene_id,
        transcript=t1_text,
        synthesize_audio=True,
    )

    turn1 = res1.turn
    assert turn1.turn_index == 1
    assert "ask_to_explain" in turn1.acts
    assert len(turn1.child_responses) == 1
    assert turn1.child_responses[0].kind == ResponseKind.EXPLAIN_BUG
    assert turn1.child_responses[0].answer == 45
    assert turn1.child_responses[0].new_state == ChildState.CAN_EXPLAIN
    assert len(turn1.child_lines) == 1
    assert turn1.child_lines[0].persona_id == "ravi"
    # Ravi's line was voiced and non-empty
    assert len(turn1.child_lines[0].line_hi) > 0
    # Stage timings recorded
    assert "tagger_ms" in turn1.stage_ms
    assert "engine_ms" in turn1.stage_ms
    assert "voice_ms" in turn1.stage_ms
    assert "tts_ms" in turn1.stage_ms
    assert turn1.stage_ms["total_ms"] >= 0
    # Outbound messages generated
    assert len(res1.outbound) >= 1

    # ── Turn 2: CONCRETE_REPRESENTATION ─────────────────────────────────
    t2_text = "रवि, तीली और बंडल से 52 बनाओ और एक बंडल खोलो।"
    res2 = await scene_runner.turn(
        scene_id=scene_id,
        transcript=t2_text,
        synthesize_audio=True,
    )

    turn2 = res2.turn
    assert turn2.turn_index == 2
    assert "concrete_representation" in turn2.acts
    assert len(turn2.child_responses) == 1
    assert turn2.child_responses[0].kind == ResponseKind.SCAFFOLDED_CORRECT
    assert turn2.child_responses[0].answer == 35
    assert turn2.child_responses[0].new_state == ChildState.PARTIAL

    # ── Turn 3: CONTRAST_TWO_ANSWERS ────────────────────────────────────
    t3_text = "रवि, पहले 45 आया था और अब 35 आया। दोनों उत्तरों की तुलना करके बताओ कौन सा सही है?"
    res3 = await scene_runner.turn(
        scene_id=scene_id,
        transcript=t3_text,
        synthesize_audio=True,
    )

    turn3 = res3.turn
    assert turn3.turn_index == 3
    assert len(turn3.child_responses) == 1
    # Ravi reaches CORRECT_EXPLAINED
    assert turn3.child_responses[0].kind == ResponseKind.CORRECT_EXPLAINED
    assert turn3.child_responses[0].new_state == ChildState.CORRECT

    # Scene state is persisted and finished
    saved_scene = await scene_runner.store.get(scene_id)
    assert saved_scene is not None
    assert len(saved_scene.turns) == 3
    # Scene ended since the child is now CORRECT
    assert saved_scene.scene_state.ended is True


@pytest.mark.asyncio
async def test_scene_runner_stop_word_ends_scene_early(scene_runner: SceneRunner) -> None:
    """Stop keywords ('बस', 'रुको', 'खत्म', 'stop') cleanly terminate the scene early."""
    teacher_id = uuid4()
    scene = await scene_runner.create_scene(teacher_id=teacher_id)
    scene_id = scene.scene_id

    res = await scene_runner.turn(
        scene_id=scene_id,
        transcript="बस, आज का अभ्यास यहीं खत्म करते हैं।",
    )

    turn = res.turn
    assert turn.ended is True
    assert turn.end_reason == "teacher_stop"
    assert "फीडबैक" in (res.outbound[0].text_hi or "")

    saved_scene = await scene_runner.store.get(scene_id)
    assert saved_scene is not None
    assert saved_scene.scene_state.ended is True
    assert saved_scene.active is False


@pytest.mark.asyncio
async def test_scene_runner_multi_child_turn(scene_runner: SceneRunner) -> None:
    """In a 3-child scene, addressing a specific child routes to that child."""
    teacher_id = uuid4()
    scene = await scene_runner.create_scene(teacher_id=teacher_id)
    scene_id = scene.scene_id

    # Turn addressed directly to Priya
    res = await scene_runner.turn(
        scene_id=scene_id,
        transcript="प्रिया, तुम बताओ तुमने 43 में से 27 कैसे घटाया?",
    )

    turn = res.turn
    assert len(turn.child_responses) >= 1
    assert turn.child_responses[0].persona_id == "priya"
    assert turn.addressed_child == "priya"


@pytest.mark.asyncio
async def test_postgres_scene_store_roundtrip() -> None:
    """Save scene + 3 turns to PostgresSceneStore -> new store instance -> get returns same scene and turns with stage_ms."""
    import os
    from unittest.mock import patch

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from backend.app.config import settings
    from backend.app.db.models import Teacher
    from backend.app.rehearsal.scene_store import PostgresSceneStore, SceneRecord, TurnRecord
    from backend.app.rule_engine.domain import (
        ChildRuntime,
        ChildState,
        Domain,
        Problem,
        SceneState,
    )

    db_url = (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/abhyas_b"
    )
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "postgresql+psycopg2://" in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")

    test_engine = create_async_engine(db_url, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    with (
        patch.object(settings, "DATABASE_URL", db_url),
        patch("backend.app.rehearsal.scene_store.async_session_factory", test_session_factory),
    ):
        teacher_id = uuid4()
        scene_id = uuid4()

        # Insert required teacher parent row for foreign key
        try:
            async with test_session_factory() as session:
                teacher = Teacher(
                    id=teacher_id,
                    name="परीक्षण शिक्षक",
                    address_form="m",
                    preferred_channel="whatsapp",
                    onboarding_state="READY",
                    is_demo=True,
                )
                session.add(teacher)
                await session.commit()
        except Exception as exc:
            pytest.skip(f"Postgres database at {db_url} not reachable: {exc}")

        try:
            store1 = PostgresSceneStore()
            state = SceneState(
                move_id="m01_place_value_intro",
                domain=Domain.NUMERACY,
                effective_acts=["ask_to_explain"],
                target_causes=["cause_1"],
                items=[Problem(type="sub", a=52, b=17)],
                current_item=Problem(type="sub", a=52, b=17),
                children=[
                    ChildRuntime(
                        persona_id="ravi",
                        misconception="SUB_SMALLER_FROM_LARGER",
                        temperament="confident",
                        state=ChildState.MISCONCEPTION,
                    )
                ],
                guess_lexicon={},
                max_turns=5,
            )

            scene_record = SceneRecord(
                scene_id=scene_id,
                teacher_id=teacher_id,
                move_id="m01_place_value_intro",
                scene_state=state,
                active=True,
            )

            # Add 3 turns with stage_ms
            for i in range(1, 4):
                turn = TurnRecord(
                    turn_index=i,
                    transcript=f"Turn transcript {i}",
                    acts=["ask_to_explain"],
                    addressed_child="ravi",
                    stage_ms={"tagger_ms": 10 * i, "engine_ms": 5 * i, "total_ms": 50 * i},
                    ended=(i == 3),
                )
                scene_record.turns.append(turn)

            await store1.save(scene_record)

            # Brand new store instance (clean in-memory cache)
            store2 = PostgresSceneStore()
            retrieved = await store2.get(scene_id)

            assert retrieved is not None
            assert retrieved.scene_id == scene_id
            assert retrieved.teacher_id == teacher_id
            assert retrieved.move_id == "m01_place_value_intro"
            assert len(retrieved.turns) == 3
            for i, t in enumerate(retrieved.turns, start=1):
                assert t.turn_index == i
                assert t.transcript == f"Turn transcript {i}"
                assert t.addressed_child == "ravi"
                assert t.stage_ms == {"tagger_ms": 10 * i, "engine_ms": 5 * i, "total_ms": 50 * i}

        finally:
            # Clean up test teacher (cascades and deletes test scene & turns)
            try:
                async with test_session_factory() as session:
                    t = await session.get(Teacher, teacher_id)
                    if t is not None:
                        await session.delete(t)
                        await session.commit()
                await test_engine.dispose()
            except Exception:
                pass
