"""Session manager for orchestrating teacher sessions and state persistence."""

import logging
from typing import Optional
from backend.app.sessions.state_machine import SessionContext, SessionStateEnum, WeeklyStateMachine

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self) -> None:
        self._in_memory_sessions: dict[str, SessionContext] = {}

    def get_or_create_session(self, teacher_id: str, week_start: str, move_id: str) -> WeeklyStateMachine:
        key = f"{teacher_id}:{week_start}"
        if key not in self._in_memory_sessions:
            ctx = SessionContext(
                teacher_id=teacher_id,
                week_start=week_start,
                current_move_id=move_id,
                current_state=SessionStateEnum.LEARN,
            )
            self._in_memory_sessions[key] = ctx
        return WeeklyStateMachine(self._in_memory_sessions[key])


session_manager = SessionManager()
