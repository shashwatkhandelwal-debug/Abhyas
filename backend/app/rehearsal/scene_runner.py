"""SceneRunner orchestrating deliberate practice rehearsal turns (spec/02 §2.2, T19).

Coordinates the multi-stage pipeline:
1. Stop word / keyword detection ("बस", "रुको", "खत्म", "stop")
2. act_tagger: tags teacher turn acts with fast model or fallback
3. RuleEngine: pure deterministic step computing ChildResponse(s)
4. child_voice: renders childlike Hindi speech guarded by guard_child_line
5. TTS: synthesizes audio for child persona voices
6. Persistence: records turns and stage timings in SceneStore
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.content_models import PersonaCard
from backend.app.core.intents import Intent, match_intent
from backend.app.core.messages import get_message
from backend.app.core.types import OutboundMessage
from backend.app.llm.roles.act_tagger import tag_act
from backend.app.llm.roles.child_voice import voice_child_line
from backend.app.rehearsal.scene_store import (
    ChildLineRecord,
    SceneRecord,
    SceneStore,
    TurnRecord,
    scene_store,
)
from backend.app.rule_engine.domain import (
    ChildResponse,
    ChildRuntime,
    ChildState,
    Domain,
    MoveCard,
    Problem,
    SceneState,
    TaggedTurn,
    TeachingAct,
)
from backend.app.rule_engine.engine import RuleEngine
from backend.app.speech.audio import AudioProcessingError
from backend.app.speech.tts import TTSError, TTSProvider, get_tts_provider
from backend.app.speech.voices import get_voice

logger = logging.getLogger("abhyas.rehearsal.scene_runner")


class TurnResult(BaseModel):
    """Result of executing one teacher turn through SceneRunner."""

    turn: TurnRecord
    outbound: list[OutboundMessage]


def load_personas(personas_dir: Path | str | None = None) -> dict[str, PersonaCard]:
    """Loads all persona cards from content/personas/ directory."""
    if personas_dir is None:
        personas_dir = Path(__file__).parents[3] / "content" / "personas"
    else:
        personas_dir = Path(personas_dir)

    personas: dict[str, PersonaCard] = {}
    if personas_dir.is_dir():
        for f in personas_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "id" in data:
                    persona = PersonaCard.model_validate(data)
                    personas[persona.id] = persona
            except Exception as exc:
                logger.warning("Failed loading persona %s: %s", f, exc)

    return personas


def load_move_card(move_id: str, moves_dir: Path | str | None = None) -> MoveCard:
    """Loads a move card from content/moves/ directory by ID."""
    if moves_dir is None:
        moves_dir = Path(__file__).parents[3] / "content" / "moves"
    else:
        moves_dir = Path(moves_dir)

    move_file = moves_dir / f"{move_id}.yaml"
    if not move_file.is_file():
        raise FileNotFoundError(f"Move card file not found: {move_file}")

    data = yaml.safe_load(move_file.read_text(encoding="utf-8"))
    return MoveCard.model_validate(data)


class SceneRunner:
    """Orchestrates interactive deliberate practice turns in REHEARSE state."""

    def __init__(
        self,
        tts_provider: TTSProvider | None = None,
        store: SceneStore | None = None,
        personas: dict[str, PersonaCard] | None = None,
    ) -> None:
        self.tts = tts_provider or get_tts_provider()
        self.store = store or scene_store
        self.personas = personas or load_personas()
        self._move_cache: dict[str, MoveCard] = {}

    def get_move(self, move_id: str) -> MoveCard:
        if move_id not in self._move_cache:
            self._move_cache[move_id] = load_move_card(move_id)
        return self._move_cache[move_id]

    async def create_scene(
        self,
        teacher_id: UUID,
        move_id: str = "NUM_SUB_REGROUP_BUNDLES",
        item: Problem | None = None,
        children: list[ChildRuntime] | None = None,
        max_turns: int | None = None,
        one_on_one_persona: str | None = None,
    ) -> SceneRecord:
        """Initializes a new rehearsal scene for a teacher.

        `one_on_one_persona` makes a single-child scene with that persona from the move card
        (one-on-one turn limit); otherwise the move's three children are used.
        """
        move = self.get_move(move_id)

        # Parse scenario items from move card
        items: list[Problem] = []
        for raw_item in move.scenario.items:
            t = raw_item.get("type", "sub")
            items.append(
                Problem(
                    type=t,
                    a=raw_item.get("a"),
                    b=raw_item.get("b"),
                    tens=raw_item.get("tens"),
                    ones=raw_item.get("ones"),
                    word=raw_item.get("word"),
                )
            )

        if item is not None:
            current_item = item
        elif items:
            current_item = items[0]
        else:
            raise ValueError(f"Move '{move_id}' has no scenario items defined in move card")

        # Construct child runtimes if not provided
        if children is None:
            children = []
            for sc in move.scenario.children:
                persona = self.personas.get(sc.persona_id)
                temperament = persona.temperament if persona else "confident"
                children.append(
                    ChildRuntime(
                        persona_id=sc.persona_id,
                        misconception=sc.misconception,
                        temperament=temperament,
                        state=ChildState.MISCONCEPTION,
                    )
                )

        if one_on_one_persona is not None:
            children = [c for c in children if c.persona_id == one_on_one_persona]
            if not children:
                raise ValueError(
                    f"Move '{move_id}' has no child '{one_on_one_persona}' in its scenario"
                )
        one_on_one = one_on_one_persona is not None
        if max_turns is None:
            max_turns = (
                settings.MAX_TURNS_ONE_ON_ONE if one_on_one else settings.MAX_TURNS_PER_REHEARSAL
            )

        scene_state = SceneState(
            move_id=move_id,
            one_on_one=one_on_one,
            domain=Domain(move.domain.value),
            # No peers in a one-on-one scene, so "involve a peer" cannot move the child
            effective_acts=[
                a
                for a in move.teaching_acts_effective
                if not (one_on_one and a == TeachingAct.INVOLVE_PEER.value)
            ],
            target_causes=move.target_causes,
            items=items,
            current_item=current_item,
            children=children,
            guess_lexicon=move.scenario.guess_lexicon,
            max_turns=max_turns,
            max_distractions=settings.MAX_DISTRACTIONS_PER_SCENE,
        )

        record = SceneRecord(
            teacher_id=teacher_id,
            move_id=move_id,
            scene_state=scene_state,
        )
        await self.store.save(record)
        return record

    async def turn(
        self,
        scene_id: UUID,
        transcript: str,
        address_form: str = "f",
        synthesize_audio: bool = True,
        on_text_ready: (
            Callable[[list[ChildLineRecord], list[OutboundMessage]], Any] | None
        ) = None,
        stt_ms: int = 0,
    ) -> TurnResult:
        """Executes one teacher turn through the 5-stage rehearsal pipeline (spec/02 §2.2)."""
        db_ms = 0
        t_db_start = time.perf_counter()
        scene = await self.store.get(scene_id)
        db_ms += int((time.perf_counter() - t_db_start) * 1000)

        if not scene:
            raise ValueError(f"Scene with ID {scene_id} not found in store")

        scene_state = scene.scene_state
        move = self.get_move(scene_state.move_id)

        # Stage 0: Stop keyword check (CHANGES 254f622 Item 6 & Item 8)
        if match_intent(transcript, in_rehearsal=True) == Intent.STOP_SCENE:
            scene_state.ended = True
            scene_state.end_reason = "teacher_stop"
            turn_record = TurnRecord(
                turn_index=scene_state.teacher_turns + 1,
                transcript=transcript,
                acts=["stop"],
                ended=True,
                end_reason="teacher_stop",
                stage_ms={
                    "stt_ms": stt_ms,
                    "act_tagger_ms": 0,
                    "tagger_ms": 0,
                    "rule_engine_ms": 0,
                    "engine_ms": 0,
                    "child_voice_ms": 0,
                    "voice_ms": 0,
                    "db_ms": db_ms,
                    "tts_ms": 0,
                    "total_ms": stt_ms + db_ms,
                },
            )
            scene.turns.append(turn_record)
            scene.active = False
            t_db_save = time.perf_counter()
            await self.store.save(scene)
            db_ms += int((time.perf_counter() - t_db_save) * 1000)
            turn_record.stage_ms["db_ms"] = db_ms
            turn_record.stage_ms["total_ms"] = stt_ms + db_ms
            return TurnResult(
                turn=turn_record,
                outbound=[
                    OutboundMessage(
                        kind="text",
                        text_hi=get_message("scene_ended_neutral", address_form),
                        speaker="coach",
                    )
                ],
            )

        # Stage 1: act_tagger
        t_stage1 = time.perf_counter()
        tag_out = await tag_act(
            transcript=transcript,
            move_title_hi=move.title_hi,
            current_item_text=scene_state.current_item.key(),
            children_list=", ".join(c.persona_id for c in scene_state.children),
            scene_persona_ids=[c.persona_id for c in scene_state.children],
            current_item=scene_state.current_item,
        )
        tagger_ms = int((time.perf_counter() - t_stage1) * 1000)

        # Stage 2: RuleEngine (log unknown acts, CHANGES 254f622 Item 10)
        t_stage2 = time.perf_counter()
        act_enums: list[TeachingAct] = []
        for a in tag_out.acts:
            try:
                act_enums.append(TeachingAct(a))
            except ValueError:
                logger.warning("Unknown teaching act encountered from tagger: %s", a)

        tagged_turn = TaggedTurn(
            acts=act_enums,
            addressed_child=tag_out.addressed_child,
            problem=tag_out.problem,
        )
        step_result = RuleEngine.step(scene_state, tagged_turn)
        engine_ms = int((time.perf_counter() - t_stage2) * 1000)

        # Stage 3: child_voice & guarding (voiced in parallel via asyncio.gather across responding children)
        t_stage3 = time.perf_counter()
        all_past_lines = [
            line.line_hi
            for past_turn in scene.turns
            for line in past_turn.child_lines
            if line.line_hi
        ]
        last_4 = all_past_lines[-4:]

        async def _voice_child(resp: ChildResponse) -> ChildLineRecord | None:
            persona = self.personas.get(resp.persona_id)
            if not persona:
                return None
            spoken_line = await voice_child_line(
                response=resp,
                persona=persona,
                last_4_lines=last_4,
                turn_idx=scene_state.teacher_turns,
                address_form=address_form,
            )
            return ChildLineRecord(
                persona_id=resp.persona_id,
                line_hi=spoken_line,
                voice_id=persona.voice_id,
            )

        voiced_records = await asyncio.gather(
            *(_voice_child(resp) for resp in step_result.responses)
        )
        child_lines: list[ChildLineRecord] = [r for r in voiced_records if r is not None]
        voice_ms = int((time.perf_counter() - t_stage3) * 1000)
        logger.info(
            "child_voice_turn_latency turn=%d stage=child_voice latency_ms=%d count=%d",
            scene_state.teacher_turns,
            voice_ms,
            len(child_lines),
        )

        # Deliver text immediately before TTS (spec/06 §6.4: perceived latency optimisation)
        if on_text_ready and child_lines:
            text_msgs = [
                OutboundMessage(
                    kind="text",
                    text_hi=line.line_hi,
                    speaker=line.persona_id,
                )
                for line in child_lines
                if line.line_hi.strip()
            ]
            if text_msgs:
                cb_res = on_text_ready(child_lines, text_msgs)
                if asyncio.iscoroutine(cb_res):
                    await cb_res

        # Stage 4: TTS synthesis running concurrently (CHANGES 254f622 Item 4 & 10)
        t_stage4 = time.perf_counter()
        outbound_messages: list[OutboundMessage] = []

        async def _synthesize_line(line_rec: ChildLineRecord) -> OutboundMessage | None:
            if not line_rec.line_hi.strip():
                return None

            voice_spec = get_voice(line_rec.voice_id)
            if synthesize_audio:
                try:
                    synth_res = await self.tts.synthesize(line_rec.line_hi, voice_spec)
                    if synth_res.audio:
                        line_rec.audio_ref = synth_res.cache_key
                        return OutboundMessage(
                            kind="audio",
                            text_hi=line_rec.line_hi,
                            audio_ref=synth_res.cache_key,
                            speaker=line_rec.persona_id,
                        )
                except (TTSError, AudioProcessingError) as exc:
                    logger.warning("TTS failed for child line, sending text only: %s", exc)
                except Exception as exc:
                    logger.warning("Unexpected error during child TTS, sending text only: %s", exc)

            return OutboundMessage(
                kind="text",
                text_hi=line_rec.line_hi,
                speaker=line_rec.persona_id,
            )

        if child_lines:
            tts_results = await asyncio.gather(*(_synthesize_line(line) for line in child_lines))
            outbound_messages.extend([m for m in tts_results if m is not None])

        tts_ms = int((time.perf_counter() - t_stage4) * 1000)

        # Stage 5: Turn persistence & updates
        t_db_save = time.perf_counter()
        total_ms = stt_ms + tagger_ms + engine_ms + voice_ms + db_ms + tts_ms
        turn_record = TurnRecord(
            turn_index=scene_state.teacher_turns,
            transcript=transcript,
            acts=[a.value for a in act_enums],
            addressed_child=tag_out.addressed_child,
            child_responses=step_result.responses,
            child_lines=child_lines,
            stage_ms={
                "stt_ms": stt_ms,
                "act_tagger_ms": tagger_ms,
                "tagger_ms": tagger_ms,
                "rule_engine_ms": engine_ms,
                "engine_ms": engine_ms,
                "child_voice_ms": voice_ms,
                "voice_ms": voice_ms,
                "db_ms": db_ms,
                "tts_ms": tts_ms,
                "total_ms": total_ms,
            },
            ended=step_result.ended,
            end_reason=step_result.end_reason,
        )

        scene.turns.append(turn_record)
        if step_result.ended:
            scene.active = False
            # Append scene completion outbound note from catalog (CHANGES 254f622 Item 8)
            end_msg_key = (
                "scene_all_correct"
                if step_result.end_reason == "all_correct"
                else "scene_ended_neutral"
            )
            end_kwargs: dict[str, str] = {}
            if scene_state.one_on_one and end_msg_key == "scene_all_correct":
                end_msg_key = "scene_all_correct_one"
                end_kwargs["child"] = get_message(f"speaker_{scene_state.children[0].persona_id}")
            outbound_messages.append(
                OutboundMessage(
                    kind="text",
                    text_hi=get_message(end_msg_key, address_form, **end_kwargs),
                    speaker="coach",
                )
            )

        await self.store.save(scene)
        db_ms += int((time.perf_counter() - t_db_save) * 1000)
        turn_record.stage_ms["db_ms"] = db_ms
        turn_record.stage_ms["total_ms"] = (
            stt_ms + tagger_ms + engine_ms + voice_ms + db_ms + tts_ms
        )
        return TurnResult(turn=turn_record, outbound=outbound_messages)


__all__ = [
    "ChildLineRecord",
    "SceneRunner",
    "TurnResult",
    "load_personas",
    "load_move_card",
]
