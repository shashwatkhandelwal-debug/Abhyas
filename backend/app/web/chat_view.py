"""What the chat header says (move title, "Step 4 of 7: Practice"), from her saved session state.

One small read of the latest `session_state` row; the page renders it and every poll refreshes it, so
the header follows the weekly loop instead of showing one fixed title.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.messages import get_message, has_message
from backend.app.db.models import SessionState, Teacher
from backend.app.rehearsal.header import preview_header
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions.path import load_induction_order
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

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
    rehearse_stage: str = "",
) -> dict[str, Any]:
    """Header texts for one teacher state. Before onboarding is finished there is no move yet."""
    if onboarding != OnboardingStateEnum.READY.value:
        return {
            "move_title": get_message("ui_step_setup"),
            "step_label": "",
            "step": 0,
            "scene_preview": None,
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
    if state in PRE_SCENE_STATES and rehearse_stage == "":
        try:
            preview = preview_header(load_move_card(move_id))
        except (FileNotFoundError, ValueError):
            preview = None
    return {
        "move_title": move_title(move_id),
        "step_label": label,
        "step": step,
        "scene_preview": preview,
    }


async def load_chat_view(db: AsyncSession, teacher: Teacher) -> dict[str, Any]:
    """Header data for this teacher from her newest session_state row."""
    found = (
        await db.execute(
            select(SessionState)
            .where(SessionState.teacher_id == uuid.UUID(str(teacher.id)))
            .order_by(SessionState.week_start.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    row = found if isinstance(found, SessionState) else None
    return build_view(
        onboarding=str(teacher.onboarding_state),
        move_id=row.move_id if row else load_induction_order()[0],
        state=row.state if row else SessionStateEnum.LEARN.value,
        prior_state=row.prior_state if row else None,
        rehearse_stage=str((row.context or {}).get("rehearse_stage", "")) if row else "",
    )
