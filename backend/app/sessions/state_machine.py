"""Session State Machine for the Weekly Loop (§4)."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.config import settings


class SessionStateEnum(StrEnum):
    PLACEMENT = "PLACEMENT"
    LEARN = "LEARN"
    EXPLAIN_BACK = "EXPLAIN_BACK"
    MODEL = "MODEL"
    REHEARSE = "REHEARSE"
    FEEDBACK = "FEEDBACK"
    TRY_IN_CLASS = "TRY_IN_CLASS"
    REFLECT = "REFLECT"
    DONE = "DONE"
    ASK = "ASK"  # Interruption state (§4, §8)


class SessionContext(BaseModel):
    teacher_id: str
    week_start: str
    current_move_id: str
    current_state: SessionStateEnum = SessionStateEnum.LEARN
    prior_state_before_ask: SessionStateEnum | None = None
    retries_count: int = 0
    rehearsal_turns_count: int = 0
    child_states: dict[str, int] = Field(default_factory=dict)
    last_inbound_at: datetime | None = None


class WeeklyStateMachine:
    """Manages legal transitions in the weekly deliberate practice loop."""

    def __init__(self, context: SessionContext):
        self.ctx = context

    def is_outside_24h_window(self) -> bool:
        """Checks if current time is outside Meta 24h customer service window."""
        if not self.ctx.last_inbound_at:
            return True
        now = datetime.now(UTC)
        diff = (now - self.ctx.last_inbound_at).total_seconds()
        return diff > 86400  # 24 hours

    def transition_to(self, new_state: SessionStateEnum) -> None:
        """Executes state transition."""
        self.ctx.current_state = new_state

    def handle_ask_interruption(self) -> None:
        """Interrupts current flow with an ASK question (§4, §8)."""
        if self.ctx.current_state != SessionStateEnum.ASK:
            self.ctx.prior_state_before_ask = self.ctx.current_state
            self.ctx.current_state = SessionStateEnum.ASK

    def resume_after_ask(self) -> SessionStateEnum:
        """Resumes previous state after answering an ASK query (§4)."""
        target = self.ctx.prior_state_before_ask or SessionStateEnum.LEARN
        self.ctx.current_state = target
        self.ctx.prior_state_before_ask = None
        return target

    def can_retry_rehearsal(self) -> bool:
        """Checks if retry limit has been reached (§4: max 3 per week)."""
        return self.ctx.retries_count < settings.MAX_REHEARSAL_RETRIES_PER_WEEK

    def advance(self) -> SessionStateEnum:
        """Advances to the natural next step in the loop."""
        transitions = {
            SessionStateEnum.PLACEMENT: SessionStateEnum.LEARN,
            SessionStateEnum.LEARN: SessionStateEnum.EXPLAIN_BACK,
            SessionStateEnum.EXPLAIN_BACK: SessionStateEnum.MODEL,
            SessionStateEnum.MODEL: SessionStateEnum.REHEARSE,
            SessionStateEnum.REHEARSE: SessionStateEnum.FEEDBACK,
            SessionStateEnum.FEEDBACK: SessionStateEnum.TRY_IN_CLASS,
            SessionStateEnum.TRY_IN_CLASS: SessionStateEnum.REFLECT,
            SessionStateEnum.REFLECT: SessionStateEnum.DONE,
        }
        if self.ctx.current_state in transitions:
            self.ctx.current_state = transitions[self.ctx.current_state]
        return self.ctx.current_state
