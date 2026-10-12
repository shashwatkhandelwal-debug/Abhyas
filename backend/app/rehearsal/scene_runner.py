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

import logging
import time
from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel

from backend.app.content_models import PersonaCard
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
from backend.app.speech.cache import compute_cache_key
from backend.app.speech.tts import TTSProvider, get_tts_provider
from backend.app.speech.voices import get_voice

logger = logging.getLogger("abhyas.rehearsal.scene_runner")

STOP_KEYWORDS = ["बस", "रुको", "खत्म", "stop", "pause", "bas", "rok", "roko"]


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

    def create_scene(
        self,
        teacher_id: UUID,
        move_id: str = "NUM_SUB_REGROUP_BUNDLES",
        item: Problem | None = None,
        children: list[ChildRuntime] | None = None,
        max_turns: int = 8,
    ) -> SceneRecord:
        """Initializes a new rehearsal scene for a teacher."""
        move = self.get_move(move_id)

        # Parse scenario items
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
        if not items:
            items = [Problem(type="sub", a=52, b=17)]

        current_item = item or items[0]

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

        scene_state = SceneState(
            move_id=move_id,
            domain=Domain(move.domain.value),
            effective_acts=move.teaching_acts_effective,
            target_causes=move.target_causes,
            items=items,
            current_item=current_item,
            children=children,
            guess_lexicon=move.scenario.guess_lexicon,
            max_turns=max_turns,
        )

        record = SceneRecord(
            teacher_id=teacher_id,
            move_id=move_id,
            scene_state=scene_state,
        )
        self.store.save(record)
        return record

    async def turn(
        self,
        scene_id: UUID,
        transcript: str,
        address_form: str = "f",
        synthesize_audio: bool = True,
    ) -> TurnResult:
        """Executes one teacher turn through the 5-stage rehearsal pipeline (spec/02 §2.2)."""
        scene = self.store.get(scene_id)
        if not scene:
            raise ValueError(f"Scene with ID {scene_id} not found in store")

        scene_state = scene.scene_state
        move = self.get_move(scene_state.move_id)

        # Stage 0: Stop keyword check
        text_lower = transcript.strip().lower()
        if any(w in text_lower for w in STOP_KEYWORDS):
            scene_state.ended = True
            scene_state.end_reason = "teacher_stop"
            turn_record = TurnRecord(
                turn_index=scene_state.teacher_turns + 1,
                transcript=transcript,
                acts=["stop"],
                ended=True,
                end_reason="teacher_stop",
                stage_ms={"total_ms": 0},
            )
            scene.turns.append(turn_record)
            scene.active = False
            self.store.save(scene)
            return TurnResult(
                turn=turn_record,
                outbound=[
                    OutboundMessage(
                        kind="text",
                        text_hi="अभ्यास यहीं समाप्त होता है। अब हम आपका फीडबैक देखते हैं।",
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

        # Stage 2: RuleEngine
        t_stage2 = time.perf_counter()
        act_enums: list[TeachingAct] = []
        for a in tag_out.acts:
            try:
                act_enums.append(TeachingAct(a))
            except ValueError:
                pass

        tagged_turn = TaggedTurn(
            acts=act_enums,
            addressed_child=tag_out.addressed_child,
            problem=tag_out.problem,
        )
        step_result = RuleEngine.step(scene_state, tagged_turn)
        engine_ms = int((time.perf_counter() - t_stage2) * 1000)

        # Stage 3: child_voice & guarding
        t_stage3 = time.perf_counter()
        child_lines: list[ChildLineRecord] = []
        last_4 = [
            line.line_hi
            for past_turn in scene.turns[-2:]
            for line in past_turn.child_lines
            if line.line_hi
        ]

        for resp in step_result.responses:
            persona = self.personas.get(resp.persona_id)
            if not persona:
                continue

            spoken_line = await voice_child_line(
                response=resp,
                persona=persona,
                last_4_lines=last_4,
                turn_idx=scene_state.teacher_turns,
                address_form=address_form,
            )

            child_lines.append(
                ChildLineRecord(
                    persona_id=resp.persona_id,
                    line_hi=spoken_line,
                    voice_id=persona.voice_id,
                )
            )
        voice_ms = int((time.perf_counter() - t_stage3) * 1000)

        # Stage 4: TTS synthesis
        t_stage4 = time.perf_counter()
        outbound_messages: list[OutboundMessage] = []

        for line_rec in child_lines:
            if not line_rec.line_hi.strip():
                continue

            voice_spec = get_voice(line_rec.voice_id)
            if synthesize_audio:
                try:
                    wav_bytes = await self.tts.synthesize(line_rec.line_hi, voice_spec)
                    if wav_bytes:
                        ckey = compute_cache_key(
                            line_rec.line_hi, voice_spec.provider_speaker, voice_spec
                        )
                        line_rec.audio_ref = ckey
                        outbound_messages.append(
                            OutboundMessage(
                                kind="audio",
                                text_hi=line_rec.line_hi,
                                audio_ref=ckey,
                                speaker=line_rec.persona_id,
                            )
                        )
                    else:
                        outbound_messages.append(
                            OutboundMessage(
                                kind="text",
                                text_hi=line_rec.line_hi,
                                speaker=line_rec.persona_id,
                            )
                        )
                except Exception as exc:
                    logger.warning("TTS failed for child line, sending text only: %s", exc)
                    outbound_messages.append(
                        OutboundMessage(
                            kind="text",
                            text_hi=line_rec.line_hi,
                            speaker=line_rec.persona_id,
                        )
                    )
            else:
                outbound_messages.append(
                    OutboundMessage(
                        kind="text",
                        text_hi=line_rec.line_hi,
                        speaker=line_rec.persona_id,
                    )
                )

        tts_ms = int((time.perf_counter() - t_stage4) * 1000)

        # Stage 5: Turn persistence & updates
        total_ms = tagger_ms + engine_ms + voice_ms + tts_ms
        turn_record = TurnRecord(
            turn_index=scene_state.teacher_turns,
            transcript=transcript,
            acts=[a.value for a in act_enums],
            addressed_child=tag_out.addressed_child,
            child_responses=step_result.responses,
            child_lines=child_lines,
            stage_ms={
                "tagger_ms": tagger_ms,
                "engine_ms": engine_ms,
                "voice_ms": voice_ms,
                "tts_ms": tts_ms,
                "total_ms": total_ms,
            },
            ended=step_result.ended,
            end_reason=step_result.end_reason,
        )

        scene.turns.append(turn_record)
        if step_result.ended:
            scene.active = False
            # Append scene completion outbound note
            outbound_messages.append(
                OutboundMessage(
                    kind="text",
                    text_hi="शाबाश! बच्चों ने सही उत्तर समझ लिया है। अब हम आपका फीडबैक देखते हैं।",
                    speaker="coach",
                )
            )

        self.store.save(scene)
        return TurnResult(turn=turn_record, outbound=outbound_messages)


__all__ = [
    "SceneRunner",
    "TurnResult",
    "load_personas",
    "load_move_card",
]
