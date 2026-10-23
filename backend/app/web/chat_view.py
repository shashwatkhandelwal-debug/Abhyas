"""What the chat header says (move title, "Step 4 of 7: Practice"), from her saved session state.

One small read of the latest `session_state` row; the page renders it and every poll refreshes it, so
the header follows the weekly loop instead of showing one fixed title.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.messages import get_message, has_message
from backend.app.db.models import Message, SessionState, Teacher
from backend.app.rehearsal.header import preview_header
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.path import load_induction_order
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum
from backend.app.web.next_action import next_action

TOTAL_STEPS = 7
PRE_SCENE_STATES = (SessionStateEnum.REHEARSE_INTRO.value, SessionStateEnum.REHEARSE.value)

# The weekly loop as she sees it: learn, say it back, hear a model, practise (the scene, retries
# included), suggestions, try it in class, reflect. ASK borrows the step she was on.
STEP_OF_STATE: dict[str, int] = {
    SessionStateEnum.LEARN.value: 1,
    SessionStateEnum.EXPLAIN_BACK.value: 2,
    SessionStateEnum.MODEL.value: 3,
    SessionStateEnum.REHEARSE_INTRO.value: 4,
    SessionStateEnum.REHEARSE.value: 4,
    SessionStateEnum.FEEDBACK.value: 5,
    SessionStateEnum.TRY_IN_CLASS.value: 6,
    SessionStateEnum.REFLECT_PEER.value: 7,
    SessionStateEnum.REFLECT_SELF.value: 7,
    SessionStateEnum.DONE.value: 7,
}


def move_title(move_id: str) -> str:
    """The move's full title in the UI language (the Hindi card title when there is no translation)."""
    key = f"move_title_{move_id}"
    if has_message(key):
        return get_message(key)
    try:
        return load_move_card(move_id).title_hi
    except FileNotFoundError:
        return move_id


def step_of(state: str, prior_state: str | None) -> int:
    """Which of the seven steps a saved state belongs to (ASK: the step she was on)."""
    if state == SessionStateEnum.ASK.value and prior_state:
        state = prior_state
    return STEP_OF_STATE.get(state, 1)


def build_view(
    *,
    onboarding: str,
    move_id: str,
    state: str,
    prior_state: str | None = None,
    context: dict[str, Any] | None = None,
    retries: int = 0,
    address_form: str = "f",
    started: bool = True,
    live_scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Header texts and the what-to-do-now line for one teacher state.

    Before onboarding is finished there is no move yet. `live_scene` is the scene bar data of a
    running scene (None when there is none); `started` says whether she has had a first reply.
    """
    ctx = context or {}
    if onboarding != OnboardingStateEnum.READY.value:
        return {
            "move_title": get_message("ui_step_setup"),
            "step_label": "",
            "step": 0,
            "scene_preview": None,
            "hint": next_action(
                onboarding=onboarding,
                state=state,
                context=ctx,
                retries=retries,
                address_form=address_form,
                started=started,
                scene=None,
            ),
        }
    step = step_of(state, prior_state)
    if state == SessionStateEnum.DONE.value:
        label = get_message("ui_step_done")
    else:
        label = get_message(
            "ui_step_label",
            n=step,
            total=TOTAL_STEPS,
            name=get_message(f"ui_step_{step}"),
        )
    # A move with no one-on-one option (literacy) starts its group scene on her first line; until
    # then the bar shows the board and the children. Numeracy creates the scene when she picks a mode.
    preview = None
    if live_scene is None and state in PRE_SCENE_STATES and ctx.get("rehearse_stage", "") == "":
        try:
            preview = preview_header(load_move_card(move_id))
        except (FileNotFoundError, ValueError):
            preview = None
    return {
        "move_title": move_title(move_id),
        "step_label": label,
        "step": step,
        "scene_preview": preview,
        "hint": next_action(
            onboarding=onboarding,
            state=state,
            context=ctx,
            retries=retries,
            address_form=address_form,
            started=started,
            scene=live_scene or preview,
        ),
    }


async def load_chat_view(
    db: AsyncSession, teacher: Teacher, live_scene: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Header data and the what-to-do-now line from her newest session_state row."""
    found = (
        await db.execute(
            select(SessionState)
            .where(SessionState.teacher_id == uuid.UUID(str(teacher.id)))
            .order_by(SessionState.week_start.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    row = found if isinstance(found, SessionState) else None
    onboarding = str(teacher.onboarding_state)
    started = True
    if onboarding == OnboardingStateEnum.NEW.value:
        # Her first words bring the welcome and the consent question: before that, "say hello"
        sent = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.teacher_id == uuid.UUID(str(teacher.id)), Message.direction == "out")
        )
        started = isinstance(sent, int) and sent > 0
    return build_view(
        onboarding=onboarding,
        move_id=row.move_id if row else load_induction_order()[0],
        state=row.state if row else SessionStateEnum.LEARN.value,
        prior_state=row.prior_state if row else None,
        context=dict(row.context or {}) if row else {},
        retries=row.rehearse_attempts if row else 0,
        address_form=str(getattr(teacher, "address_form", "f") or "f"),
        started=started,
        live_scene=live_scene,
    )
