"""Setup steps before a rehearsal scene: pick the mode, pick the child, diagnose, then talk.

Stages (kept in the session context, `rehearse_stage`): "" (no setup: legacy / group-only move),
"choose_mode" (1-1 child or three children), "choose_child" (Ravi, Priya or Aman), "diagnose"
(the teacher says what they think the child's mistake is), "scene" (the scene is running).

The 1-1 scene is created when the child is chosen; the child's misconception is shown only after
the diagnosis (or after the teacher skips it).
"""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from backend.app.content_models import MoveCard
from backend.app.core.intents import Intent, match_intent
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.core.types import Button, OutboundMessage
from backend.app.rehearsal.diagnosis import (
    DiagnosisResult,
    Verdict,
    diagnose,
    normalize_diagnosis_text,
)
from backend.app.rehearsal.scene_runner import SceneRunner
from backend.app.rehearsal.scene_store import InMemorySceneStore, PostgresSceneStore
from backend.app.rule_engine.bugs import get_rule_info
from backend.app.rule_engine.domain import Problem, SceneState
from backend.app.sessions.state_machine import SessionContext

if TYPE_CHECKING:
    from uuid import UUID

STAGE_NONE = ""
STAGE_CHOOSE_MODE = "choose_mode"
STAGE_CHOOSE_CHILD = "choose_child"
STAGE_DIAGNOSE = "diagnose"
STAGE_SCENE = "scene"
SETUP_STAGES = (STAGE_CHOOSE_MODE, STAGE_CHOOSE_CHILD, STAGE_DIAGNOSE)

MODE_ONE_ON_ONE = "one_on_one"
MODE_GROUP = "group"

BTN_ONE = "btn_rehearse_one"
BTN_GROUP = "btn_rehearse_group"
BTN_CHILD_PREFIX = "btn_child_"


def child_name(persona_id: str) -> str:
    return get_message(f"speaker_{persona_id}")


def _is_english() -> bool:
    return get_ui_lang() == "en"


def _mode_buttons(af: str) -> list[Button]:
    return [
        Button(id=BTN_ONE, title_hi=get_message(BTN_ONE, af)),
        Button(id=BTN_GROUP, title_hi=get_message(BTN_GROUP, af)),
    ]


def _child_buttons(move: MoveCard, af: str) -> list[Button]:
    return [
        Button(
            id=f"{BTN_CHILD_PREFIX}{c.persona_id}",
            title_hi=get_message(f"{BTN_CHILD_PREFIX}{c.persona_id}", af),
        )
        for c in move.scenario.children
    ]


def supports_one_on_one(move: MoveCard) -> bool:
    return move.rubric_one_on_one is not None


def begin_setup(ctx: SessionContext, move: MoveCard) -> list[OutboundMessage]:
    """Called when the week enters REHEARSE_INTRO: the mode prompt, or the old group intro."""
    af = ctx.address_form
    ctx.rehearse_mode = ""
    ctx.rehearse_child = ""
    ctx.diagnosis = {}
    if not supports_one_on_one(move):
        ctx.rehearse_stage = STAGE_NONE
        return [
            OutboundMessage(
                kind="text",
                text_hi=get_message("rehearse_intro", af, scene_intro=move.scenario.intro_hi),
            )
        ]
    ctx.rehearse_stage = STAGE_CHOOSE_MODE
    return [
        OutboundMessage(
            kind="buttons",
            text_hi=get_message("rehearse_mode_prompt", af),
            buttons=_mode_buttons(af),
        )
    ]


def _matches_child(text: str, persona_id: str) -> bool:
    cleaned = unicodedata.normalize("NFC", text).strip().lower()
    names = {persona_id, get_message(f"speaker_{persona_id}", lang="hi").lower()}
    names.add(get_message(f"speaker_{persona_id}", lang="en").lower())
    return any(n and n in cleaned for n in names)


def _typed_mode(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in ("1", "1-1", "one", "one-on-one", "single"):
        return MODE_ONE_ON_ONE
    if cleaned in ("3", "three", "group"):
        return MODE_GROUP
    return None


def wrong_answer_for(misconception: str, item: Problem) -> int | str:
    """The child's wrong answer on the board item (rule engine output, never an LLM)."""
    return get_rule_info(misconception).fn(item, {"guess_lexicon": {}}).answer


def intro_text(move: MoveCard, persona_id: str, scene_state: SceneState) -> str:
    item = scene_state.current_item
    misconception = scene_state.children[0].misconception
    template = move.one_on_one_intro_en if _is_english() else move.one_on_one_intro_hi
    return template.format(
        child=child_name(persona_id),
        a=item.a,
        b=item.b,
        tens=item.tens,
        ones=item.ones,
        answer=wrong_answer_for(misconception, item),
    )


async def handle_setup(
    *,
    ctx: SessionContext,
    teacher_id: UUID,
    move: MoveCard,
    runner: SceneRunner,
    store: InMemorySceneStore | PostgresSceneStore,
    matched_intent: Intent | None,
    btn_id: str | None,
    text: str,
) -> list[OutboundMessage]:
    """One teacher message during setup. The caller persists `ctx` afterwards."""
    af = ctx.address_form

    if ctx.rehearse_stage != STAGE_CHOOSE_MODE and (
        match_intent(text, in_rehearsal=True) == Intent.STOP_SCENE
    ):
        # "End practice" before the scene started: drop the scene and offer the choice again
        await _end_active_scene(store, teacher_id)
        return begin_setup(ctx, move)

    if ctx.rehearse_stage == STAGE_CHOOSE_MODE:
        mode = (
            MODE_ONE_ON_ONE
            if btn_id == BTN_ONE
            else MODE_GROUP
            if btn_id == BTN_GROUP
            else _typed_mode(text)
        )
        if mode == MODE_GROUP:
            await _end_active_scene(store, teacher_id)
            await runner.create_scene(teacher_id=teacher_id, move_id=ctx.current_move_id)
            ctx.rehearse_mode = MODE_GROUP
            ctx.rehearse_stage = STAGE_SCENE
            return [
                OutboundMessage(
                    kind="text",
                    text_hi=get_message("rehearse_intro", af, scene_intro=move.scenario.intro_hi),
                )
            ]
        if mode == MODE_ONE_ON_ONE:
            ctx.rehearse_mode = MODE_ONE_ON_ONE
            ctx.rehearse_stage = STAGE_CHOOSE_CHILD
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message("rehearse_child_prompt", af),
                    buttons=_child_buttons(move, af),
                )
            ]
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=get_message("rehearse_mode_unclear", af),
                buttons=_mode_buttons(af),
            )
        ]

    if ctx.rehearse_stage == STAGE_CHOOSE_CHILD:
        chosen: str | None = None
        for child in move.scenario.children:
            if btn_id == f"{BTN_CHILD_PREFIX}{child.persona_id}" or _matches_child(
                text, child.persona_id
            ):
                chosen = child.persona_id
                break
        if chosen is None:
            return [
                OutboundMessage(
                    kind="buttons",
                    text_hi=get_message("rehearse_child_unclear", af),
                    buttons=_child_buttons(move, af),
                )
            ]
        await _end_active_scene(store, teacher_id)
        record = await runner.create_scene(
            teacher_id=teacher_id, move_id=ctx.current_move_id, one_on_one_persona=chosen
        )
        record.scene_state.diagnosing = True
        await store.save(record)
        ctx.rehearse_child = chosen
        ctx.rehearse_stage = STAGE_DIAGNOSE
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=intro_text(move, chosen, record.scene_state),
                buttons=[Button(id="btn_skip", title_hi=get_message("btn_skip", af))],
            )
        ]

    # STAGE_DIAGNOSE
    active = await store.get_active_for_teacher(teacher_id)
    persona_id = ctx.rehearse_child
    if active is None or not active.scene_state.one_on_one:
        # The scene is gone (restart, expiry): start the setup again rather than guess.
        return begin_setup(ctx, move)
    true_misconception = active.scene_state.children[0].misconception
    name = child_name(persona_id)
    skipped = btn_id == "btn_skip" or matched_intent == Intent.SKIP
    if not skipped and not normalize_diagnosis_text(text):
        return [
            OutboundMessage(
                kind="buttons",
                text_hi=get_message("diagnose_empty", af, child=name),
                buttons=[Button(id="btn_skip", title_hi=get_message("btn_skip", af))],
            )
        ]
    if skipped:
        result = DiagnosisResult(
            verdict=Verdict.WRONG, true_misconception=true_misconception, reason="empty"
        )
    else:
        result = await diagnose(text, move, true_misconception)
    ctx.diagnosis = {**result.model_dump(mode="json"), "skipped": skipped}

    content = move.misconceptions[true_misconception]
    reveal = (content.reveal_en if _is_english() else content.reveal_hi).format(child=name)
    key = "diag_result_skipped" if skipped else f"diag_result_{result.verdict.value}"
    active.scene_state.diagnosing = False
    await store.save(active)
    ctx.rehearse_stage = STAGE_SCENE
    return [
        OutboundMessage(kind="text", text_hi=get_message(key, af, reveal=reveal)),
        OutboundMessage(kind="text", text_hi=get_message("rehearse_one_start", af, child=name)),
    ]


async def _end_active_scene(
    store: InMemorySceneStore | PostgresSceneStore, teacher_id: UUID
) -> None:
    """An old unfinished scene must not be picked up as the teacher's active one."""
    old = await store.get_active_for_teacher(teacher_id)
    if old is not None:
        old.active = False
        old.scene_state.ended = True
        old.scene_state.end_reason = old.scene_state.end_reason or "teacher_stop"
        await store.save(old)


__all__ = [
    "BTN_CHILD_PREFIX",
    "BTN_GROUP",
    "BTN_ONE",
    "MODE_GROUP",
    "MODE_ONE_ON_ONE",
    "SETUP_STAGES",
    "STAGE_CHOOSE_CHILD",
    "STAGE_CHOOSE_MODE",
    "STAGE_DIAGNOSE",
    "STAGE_NONE",
    "STAGE_SCENE",
    "begin_setup",
    "child_name",
    "handle_setup",
    "supports_one_on_one",
]
