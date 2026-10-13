"""Session State Machine for the Weekly Loop and Onboarding (spec/08 §8.1–§8.4, T20)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.config import settings


class SessionStateEnum(StrEnum):
    """Weekly loop session states (spec/08 §8.2)."""

    LEARN = "LEARN"
    EXPLAIN_BACK = "EXPLAIN_BACK"
    MODEL = "MODEL"
    REHEARSE = "REHEARSE"
    FEEDBACK = "FEEDBACK"
    RETRY = "RETRY"
    TRY_IN_CLASS = "TRY_IN_CLASS"
    REFLECT = "REFLECT"
    DONE = "DONE"
    ASK = "ASK"  # Interruption state (spec/08 §8.4)
    PLACEMENT = "PLACEMENT"  # Placement mode (spec/08 §8.1)


WEEKLY_LOOP_STATES: tuple[SessionStateEnum, ...] = (
    SessionStateEnum.LEARN,
    SessionStateEnum.EXPLAIN_BACK,
    SessionStateEnum.MODEL,
    SessionStateEnum.REHEARSE,
    SessionStateEnum.FEEDBACK,
    SessionStateEnum.RETRY,
    SessionStateEnum.TRY_IN_CLASS,
    SessionStateEnum.REFLECT,
    SessionStateEnum.DONE,
)


class OnboardingStateEnum(StrEnum):
    """Teacher onboarding states (spec/08 §8.1)."""

    NEW = "NEW"
    JOIN_CODE = "JOIN_CODE"
    PROFILE_NAME = "PROFILE_NAME"
    PROFILE_ADDRESS = "PROFILE_ADDRESS"
    PROFILE_EXPERIENCE = "PROFILE_EXPERIENCE"
    PROFILE_CLASSES = "PROFILE_CLASSES"
    SHARE_CONSENT = "SHARE_CONSENT"
    PLACEMENT_INTRO = "PLACEMENT_INTRO"
    PLACEMENT = "PLACEMENT"
    READY = "READY"


STATE_PROMPT_KEYS: dict[str, str] = {
    SessionStateEnum.LEARN: "learn_intro",
    SessionStateEnum.EXPLAIN_BACK: "explain_back_prompt",
    SessionStateEnum.MODEL: "model_offer",
    SessionStateEnum.REHEARSE: "rehearse_intro",
    SessionStateEnum.FEEDBACK: "feedback_header",
    SessionStateEnum.RETRY: "rehearse_intro",
    SessionStateEnum.TRY_IN_CLASS: "try_in_class",
    SessionStateEnum.REFLECT: "reflect_q",
    SessionStateEnum.DONE: "week_done",
    SessionStateEnum.ASK: "ask_prompt",
    SessionStateEnum.PLACEMENT: "placement_intro",
}

ONBOARDING_PROMPT_KEYS: dict[str, str] = {
    OnboardingStateEnum.NEW: "welcome",
    OnboardingStateEnum.JOIN_CODE: "ask_join_code",
    OnboardingStateEnum.PROFILE_NAME: "ask_name",
    OnboardingStateEnum.PROFILE_ADDRESS: "ask_address_form",
    OnboardingStateEnum.PROFILE_EXPERIENCE: "ask_experience",
    OnboardingStateEnum.PROFILE_CLASSES: "ask_classes",
    OnboardingStateEnum.SHARE_CONSENT: "consent_share_scores",
    OnboardingStateEnum.PLACEMENT_INTRO: "placement_intro",
    OnboardingStateEnum.PLACEMENT: "placement_intro",
    OnboardingStateEnum.READY: "ready_first_move",
}


@dataclass(frozen=True)
class TransitionEdge:
    """Represents a declarative transition edge for state machine verification."""

    source_state: str
    input_kind: str
    target_state: str
    message_keys: tuple[str, ...]
    description: str = ""


# Table of valid transitions per spec/08 §8.1–§8.4
STATE_TRANSITION_TABLE: tuple[TransitionEdge, ...] = (
    # Onboarding (§8.1)
    TransitionEdge(
        source_state="NEW",
        input_kind="btn_agree",
        target_state="JOIN_CODE",
        message_keys=("ask_join_code",),
        description="Teacher agrees to service consent",
    ),
    TransitionEdge(
        source_state="NEW",
        input_kind="btn_more",
        target_state="NEW",
        message_keys=("consent_details",),
        description="Teacher asks for more consent details",
    ),
    TransitionEdge(
        source_state="NEW",
        input_kind="btn_decline",
        target_state="NEW",
        message_keys=("consent_declined",),
        description="Teacher declines service consent",
    ),
    TransitionEdge(
        source_state="JOIN_CODE",
        input_kind="valid_code",
        target_state="PROFILE_NAME",
        message_keys=("ask_name",),
        description="Teacher provides valid invite code",
    ),
    TransitionEdge(
        source_state="JOIN_CODE",
        input_kind="no_code",
        target_state="PROFILE_NAME",
        message_keys=("ask_name",),
        description="Teacher does not have join code",
    ),
    TransitionEdge(
        source_state="JOIN_CODE",
        input_kind="invalid_code",
        target_state="JOIN_CODE",
        message_keys=("join_code_invalid",),
        description="Teacher provides invalid join code",
    ),
    TransitionEdge(
        source_state="PROFILE_NAME",
        input_kind="name_text",
        target_state="PROFILE_ADDRESS",
        message_keys=("ask_address_form",),
        description="Teacher provides name",
    ),
    TransitionEdge(
        source_state="PROFILE_ADDRESS",
        input_kind="btn_female",
        target_state="PROFILE_EXPERIENCE",
        message_keys=("ask_experience",),
        description="Teacher selects female honorific (शिक्षिका)",
    ),
    TransitionEdge(
        source_state="PROFILE_ADDRESS",
        input_kind="btn_male",
        target_state="PROFILE_EXPERIENCE",
        message_keys=("ask_experience",),
        description="Teacher selects male honorific (शिक्षक)",
    ),
    TransitionEdge(
        source_state="PROFILE_EXPERIENCE",
        input_kind="exp_0_1",
        target_state="PROFILE_CLASSES",
        message_keys=("ask_classes",),
        description="Teacher selects 0-1 years (first year)",
    ),
    TransitionEdge(
        source_state="PROFILE_EXPERIENCE",
        input_kind="exp_2_5",
        target_state="PROFILE_CLASSES",
        message_keys=("ask_classes",),
        description="Teacher selects 2-5 years",
    ),
    TransitionEdge(
        source_state="PROFILE_CLASSES",
        input_kind="classes_choice",
        target_state="SHARE_CONSENT",
        message_keys=("consent_share_scores",),
        description="Teacher selects grades taught",
    ),
    TransitionEdge(
        source_state="SHARE_CONSENT",
        input_kind="btn_yes",
        target_state="PLACEMENT_INTRO",
        message_keys=("placement_intro",),
        description="Teacher consents to score sharing",
    ),
    TransitionEdge(
        source_state="SHARE_CONSENT",
        input_kind="btn_no",
        target_state="PLACEMENT_INTRO",
        message_keys=("placement_intro",),
        description="Teacher declines score sharing",
    ),
    TransitionEdge(
        source_state="PLACEMENT_INTRO",
        input_kind="turn_input",
        target_state="PLACEMENT",
        message_keys=("placement_intro",),
        description="Teacher starts placement turn 1",
    ),
    TransitionEdge(
        source_state="PLACEMENT",
        input_kind="turn_1",
        target_state="PLACEMENT",
        message_keys=(),
        description="Teacher completes placement turn 1",
    ),
    TransitionEdge(
        source_state="PLACEMENT",
        input_kind="turn_2",
        target_state="READY",
        message_keys=("placement_done", "ready_first_move"),
        description="Teacher completes placement turn 2",
    ),
    TransitionEdge(
        source_state="READY",
        input_kind="start",
        target_state="LEARN",
        message_keys=("learn_intro",),
        description="Teacher begins first weekly move",
    ),
    # Weekly loop (§8.2)
    TransitionEdge(
        source_state="LEARN",
        input_kind="btn_understood",
        target_state="EXPLAIN_BACK",
        message_keys=("explain_back_prompt",),
        description="Teacher understood learn script and advances",
    ),
    TransitionEdge(
        source_state="LEARN",
        input_kind="btn_replay",
        target_state="LEARN",
        message_keys=("learn_intro",),
        description="Teacher replays learn script audio",
    ),
    TransitionEdge(
        source_state="EXPLAIN_BACK",
        input_kind="explanation_text",
        target_state="MODEL",
        message_keys=("explain_back_reply", "model_offer"),
        description="Teacher submits 1-minute explain back audio/text",
    ),
    TransitionEdge(
        source_state="EXPLAIN_BACK",
        input_kind="btn_skip",
        target_state="MODEL",
        message_keys=("model_offer",),
        description="Teacher skips explain back",
    ),
    TransitionEdge(
        source_state="MODEL",
        input_kind="btn_listen",
        target_state="REHEARSE",
        message_keys=("model_header", "rehearse_intro"),
        description="Teacher listens to model teacher rehearsal",
    ),
    TransitionEdge(
        source_state="MODEL",
        input_kind="btn_skip",
        target_state="REHEARSE",
        message_keys=("rehearse_intro",),
        description="Teacher skips model audio and goes to rehearsal",
    ),
    TransitionEdge(
        source_state="REHEARSE",
        input_kind="teacher_turn",
        target_state="REHEARSE",
        message_keys=(),
        description="Teacher executes a deliberate practice rehearsal turn",
    ),
    TransitionEdge(
        source_state="REHEARSE",
        input_kind="stop_scene",
        target_state="FEEDBACK",
        message_keys=("feedback_header", "realism_prompt"),
        description="Teacher finishes rehearsal via stop word or scene end",
    ),
    TransitionEdge(
        source_state="FEEDBACK",
        input_kind="btn_retry",
        target_state="RETRY",
        message_keys=("rehearse_intro",),
        description="Teacher requests rehearsal retry within attempt limit",
    ),
    TransitionEdge(
        source_state="FEEDBACK",
        input_kind="retry_limit_reached",
        target_state="TRY_IN_CLASS",
        message_keys=("retry_limit", "try_in_class"),
        description="Teacher hits 3-retry weekly limit",
    ),
    TransitionEdge(
        source_state="FEEDBACK",
        input_kind="btn_continue",
        target_state="TRY_IN_CLASS",
        message_keys=("try_in_class",),
        description="Teacher accepts feedback and advances to try in class",
    ),
    TransitionEdge(
        source_state="RETRY",
        input_kind="start_rehearsal",
        target_state="REHEARSE",
        message_keys=("rehearse_intro",),
        description="Teacher begins new rehearsal attempt from retry",
    ),
    TransitionEdge(
        source_state="RETRY",
        input_kind="btn_continue",
        target_state="TRY_IN_CLASS",
        message_keys=("try_in_class",),
        description="Teacher bypasses retry and continues",
    ),
    TransitionEdge(
        source_state="TRY_IN_CLASS",
        input_kind="btn_peer",
        target_state="REFLECT",
        message_keys=("peer_item",),
        description="Teacher selects peer observation reflection path",
    ),
    TransitionEdge(
        source_state="TRY_IN_CLASS",
        input_kind="btn_self",
        target_state="REFLECT",
        message_keys=("reflect_q",),
        description="Teacher selects self reflection path",
    ),
    TransitionEdge(
        source_state="TRY_IN_CLASS",
        input_kind="btn_later",
        target_state="TRY_IN_CLASS",
        message_keys=("reminder",),
        description="Teacher defers classroom tryout",
    ),
    TransitionEdge(
        source_state="REFLECT",
        input_kind="reflection_done",
        target_state="DONE",
        message_keys=("week_done",),
        description="Teacher submits reflection, reaching evidence level 2/3",
    ),
    TransitionEdge(
        source_state="DONE",
        input_kind="btn_next_move",
        target_state="LEARN",
        message_keys=("learn_intro",),
        description="Teacher advances to next weekly move",
    ),
    TransitionEdge(
        source_state="DONE",
        input_kind="btn_progress",
        target_state="DONE",
        message_keys=("progress_summary",),
        description="Teacher requests progress summary",
    ),
    # Global Intents (§8.3–§8.4)
    TransitionEdge(
        source_state="LEARN",
        input_kind="ask",
        target_state="ASK",
        message_keys=("ask_prompt",),
        description="Teacher asks coach question, interrupting flow",
    ),
    TransitionEdge(
        source_state="ASK",
        input_kind="resume",
        target_state="LEARN",
        message_keys=("ask_resume", "learn_intro"),
        description="Teacher resumes original state after coach answer",
    ),
    TransitionEdge(
        source_state="LEARN",
        input_kind="help",
        target_state="LEARN",
        message_keys=("help_menu",),
        description="Teacher requests help menu",
    ),
    TransitionEdge(
        source_state="LEARN",
        input_kind="lite_toggle",
        target_state="LEARN",
        message_keys=("lite_on",),
        description="Teacher toggles lite mode",
    ),
    TransitionEdge(
        source_state="LEARN",
        input_kind="delete",
        target_state="NEW",
        message_keys=("data_deleted",),
        description="Teacher deletes all data and resets to NEW",
    ),
)


class TransitionResult(BaseModel):
    """Result of a state transition."""

    previous_state: str
    new_state: str
    message_keys: list[str] = Field(default_factory=list)
    evidence_level: int | None = None
    resumed: bool = False


class SessionContext(BaseModel):
    """Context state tracking weekly deliberative practice loop and onboarding (spec/08)."""

    teacher_id: str
    week_start: str
    current_move_id: str
    current_state: SessionStateEnum = SessionStateEnum.LEARN
    prior_state_before_ask: SessionStateEnum | None = None
    onboarding_state: OnboardingStateEnum = OnboardingStateEnum.NEW
    retries_count: int = 0
    rehearsal_turns_count: int = 0
    placement_turns_count: int = 0
    reflection_type: str | None = None  # "self" or "peer"
    evidence_level: int = 0
    child_states: dict[str, int] = Field(default_factory=dict)
    last_inbound_at: datetime | None = None
    lite_mode: bool = False
    address_form: str = "f"
    name: str | None = None
    cluster_id: str | None = None
    experience_band: str | None = None
    first_year: bool = False
    classes: list[int] = Field(default_factory=list)


class WeeklyStateMachine:
    """Manages legal transitions in the weekly deliberate practice loop (spec/08 §8.2)."""

    def __init__(self, context: SessionContext) -> None:
        self.ctx = context

    def is_outside_24h_window(self) -> bool:
        """Checks if current time is outside Meta 24h customer service window (spec/08 §8.6, §8.8)."""
        if not self.ctx.last_inbound_at:
            return True
        now = datetime.now(UTC)
        diff = (now - self.ctx.last_inbound_at).total_seconds()
        return diff > 86400  # 24 hours

    def is_inactive_resume(self) -> bool:
        """Checks if teacher was inactive > 6 h in a mid-week state (spec/08 §8.2)."""
        if not self.ctx.last_inbound_at:
            return False
        if self.ctx.current_state in (SessionStateEnum.DONE, SessionStateEnum.LEARN):
            return False
        now = datetime.now(UTC)
        diff = (now - self.ctx.last_inbound_at).total_seconds()
        return diff > 21600  # 6 hours

    def transition_to(self, new_state: SessionStateEnum) -> None:
        """Executes state transition directly."""
        self.ctx.current_state = new_state

    def handle_ask_interruption(self) -> None:
        """Interrupts current flow with an ASK question (spec/08 §8.4, §8.8)."""
        if self.ctx.current_state != SessionStateEnum.ASK:
            self.ctx.prior_state_before_ask = self.ctx.current_state
            self.ctx.current_state = SessionStateEnum.ASK

    def resume_after_ask(self) -> SessionStateEnum:
        """Resumes previous state after answering an ASK query (spec/08 §8.4, §8.8)."""
        target = self.ctx.prior_state_before_ask or SessionStateEnum.LEARN
        self.ctx.current_state = target
        self.ctx.prior_state_before_ask = None
        return target

    def can_retry_rehearsal(self) -> bool:
        """Checks if retry limit has been reached (spec/08 §8.2: max 3 per week)."""
        return self.ctx.retries_count < settings.MAX_REHEARSAL_RETRIES_PER_WEEK

    def get_state_prompt_key(self, state: SessionStateEnum | str | None = None) -> str:
        """Returns primary message prompt key for state (spec/08 §8.2)."""
        target_state = state if state is not None else self.ctx.current_state
        return STATE_PROMPT_KEYS.get(str(target_state), "learn_intro")

    def advance(self) -> SessionStateEnum:
        """Advances to the natural next step in the loop."""
        transitions: dict[SessionStateEnum, SessionStateEnum] = {
            SessionStateEnum.PLACEMENT: SessionStateEnum.LEARN,
            SessionStateEnum.LEARN: SessionStateEnum.EXPLAIN_BACK,
            SessionStateEnum.EXPLAIN_BACK: SessionStateEnum.MODEL,
            SessionStateEnum.MODEL: SessionStateEnum.REHEARSE,
            SessionStateEnum.REHEARSE: SessionStateEnum.FEEDBACK,
            SessionStateEnum.FEEDBACK: SessionStateEnum.TRY_IN_CLASS,
            SessionStateEnum.RETRY: SessionStateEnum.REHEARSE,
            SessionStateEnum.TRY_IN_CLASS: SessionStateEnum.REFLECT,
            SessionStateEnum.REFLECT: SessionStateEnum.DONE,
        }
        if self.ctx.current_state in transitions:
            self.ctx.current_state = transitions[self.ctx.current_state]
        return self.ctx.current_state

    def reset(self) -> None:
        """Resets teacher session data to initial state (e.g. data delete flow, spec/08 §8.3)."""
        self.ctx.current_state = SessionStateEnum.LEARN
        self.ctx.prior_state_before_ask = None
        self.ctx.onboarding_state = OnboardingStateEnum.NEW
        self.ctx.retries_count = 0
        self.ctx.rehearsal_turns_count = 0
        self.ctx.placement_turns_count = 0
        self.ctx.reflection_type = None
        self.ctx.evidence_level = 0
        self.ctx.child_states = {}
        self.ctx.name = None
        self.ctx.cluster_id = None
        self.ctx.experience_band = None
        self.ctx.first_year = False
        self.ctx.classes = []

    def transition(self, input_text_or_btn: str, intent: str | None = None) -> TransitionResult:
        """Processes input or intent against the weekly state machine (spec/08 §8.2–§8.4)."""
        token = (intent or input_text_or_btn).strip().lower()
        prev = self.ctx.current_state

        # Global intents (§8.3)
        if token in ("help", "मदद", "menu", "मेनू"):
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=["help_menu"],
            )

        if token in ("lite_toggle", "लाइट मोड", "lite"):
            self.ctx.lite_mode = not self.ctx.lite_mode
            key = "lite_on" if self.ctx.lite_mode else "lite_off"
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=[key],
            )

        if token in ("progress", "प्रगति", "btn_progress"):
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=["progress_summary"],
            )

        if token in ("ask", "सवाल", "प्रश्न", "question", "sawal", "btn_ask"):
            self.handle_ask_interruption()
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(SessionStateEnum.ASK),
                message_keys=["ask_prompt"],
            )

        if token in ("delete", "मेरा डेटा हटाएँ", "delete my data"):
            self.reset()
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.NEW),
                message_keys=["data_deleted"],
            )

        # In ASK state -> resume prior state (§8.4)
        if prev == SessionStateEnum.ASK:
            resumed = self.resume_after_ask()
            prompt_key = self.get_state_prompt_key(resumed)
            return TransitionResult(
                previous_state=str(SessionStateEnum.ASK),
                new_state=str(resumed),
                message_keys=["ask_resume", prompt_key],
                resumed=True,
            )

        # State-specific transitions (§8.2)
        if prev == SessionStateEnum.LEARN:
            if token in ("btn_replay", "replay", "repeat", "फिर से", "दोबारा"):
                return TransitionResult(
                    previous_state=str(SessionStateEnum.LEARN),
                    new_state=str(SessionStateEnum.LEARN),
                    message_keys=["learn_intro"],
                )
            self.ctx.current_state = SessionStateEnum.EXPLAIN_BACK
            return TransitionResult(
                previous_state=str(SessionStateEnum.LEARN),
                new_state=str(SessionStateEnum.EXPLAIN_BACK),
                message_keys=["explain_back_prompt"],
            )

        if prev == SessionStateEnum.EXPLAIN_BACK:
            self.ctx.current_state = SessionStateEnum.MODEL
            if token in ("btn_skip", "skip", "छोड़ें", "chhodo"):
                return TransitionResult(
                    previous_state=str(SessionStateEnum.EXPLAIN_BACK),
                    new_state=str(SessionStateEnum.MODEL),
                    message_keys=["model_offer"],
                )
            return TransitionResult(
                previous_state=str(SessionStateEnum.EXPLAIN_BACK),
                new_state=str(SessionStateEnum.MODEL),
                message_keys=["explain_back_reply", "model_offer"],
            )

        if prev == SessionStateEnum.MODEL:
            self.ctx.current_state = SessionStateEnum.REHEARSE
            if token in ("btn_listen", "listen", "सुनें"):
                return TransitionResult(
                    previous_state=str(SessionStateEnum.MODEL),
                    new_state=str(SessionStateEnum.REHEARSE),
                    message_keys=["model_header", "rehearse_intro"],
                )
            return TransitionResult(
                previous_state=str(SessionStateEnum.MODEL),
                new_state=str(SessionStateEnum.REHEARSE),
                message_keys=["rehearse_intro"],
            )

        if prev == SessionStateEnum.REHEARSE:
            if token in ("stop_scene", "बस", "रुको", "खत्म", "stop", "bas"):
                self.ctx.current_state = SessionStateEnum.FEEDBACK
                ev = 1 if self.ctx.rehearsal_turns_count >= 3 else 0
                if ev > 0:
                    self.ctx.evidence_level = max(self.ctx.evidence_level, 1)
                return TransitionResult(
                    previous_state=str(SessionStateEnum.REHEARSE),
                    new_state=str(SessionStateEnum.FEEDBACK),
                    message_keys=["feedback_header", "realism_prompt"],
                    evidence_level=ev,
                )
            # Normal rehearsal turn
            self.ctx.rehearsal_turns_count += 1
            return TransitionResult(
                previous_state=str(SessionStateEnum.REHEARSE),
                new_state=str(SessionStateEnum.REHEARSE),
                message_keys=[],
            )

        if prev == SessionStateEnum.FEEDBACK:
            if token in ("btn_retry", "retry", "फिर से अभ्यास", "retry_limit_reached"):
                if self.can_retry_rehearsal():
                    self.ctx.retries_count += 1
                    self.ctx.current_state = SessionStateEnum.RETRY
                    return TransitionResult(
                        previous_state=str(SessionStateEnum.FEEDBACK),
                        new_state=str(SessionStateEnum.RETRY),
                        message_keys=["rehearse_intro"],
                    )
                self.ctx.current_state = SessionStateEnum.TRY_IN_CLASS
                return TransitionResult(
                    previous_state=str(SessionStateEnum.FEEDBACK),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["retry_limit", "try_in_class"],
                )
            self.ctx.current_state = SessionStateEnum.TRY_IN_CLASS
            return TransitionResult(
                previous_state=str(SessionStateEnum.FEEDBACK),
                new_state=str(SessionStateEnum.TRY_IN_CLASS),
                message_keys=["try_in_class"],
            )

        if prev == SessionStateEnum.RETRY:
            if token in ("btn_continue", "continue", "आगे बढ़ें"):
                self.ctx.current_state = SessionStateEnum.TRY_IN_CLASS
                return TransitionResult(
                    previous_state=str(SessionStateEnum.RETRY),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["try_in_class"],
                )
            self.ctx.current_state = SessionStateEnum.REHEARSE
            return TransitionResult(
                previous_state=str(SessionStateEnum.RETRY),
                new_state=str(SessionStateEnum.REHEARSE),
                message_keys=["rehearse_intro"],
            )

        if prev == SessionStateEnum.TRY_IN_CLASS:
            if token in ("btn_peer", "peer", "साथी ने देखा"):
                self.ctx.reflection_type = "peer"
                self.ctx.current_state = SessionStateEnum.REFLECT
                return TransitionResult(
                    previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                    new_state=str(SessionStateEnum.REFLECT),
                    message_keys=["peer_item"],
                )
            if token in ("btn_self", "self", "खुद बताऊँगी", "खुद बताऊँगा"):
                self.ctx.reflection_type = "self"
                self.ctx.current_state = SessionStateEnum.REFLECT
                return TransitionResult(
                    previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                    new_state=str(SessionStateEnum.REFLECT),
                    message_keys=["reflect_q"],
                )
            if token in ("btn_later", "later", "बाद में"):
                return TransitionResult(
                    previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["reminder"],
                )
            self.ctx.current_state = SessionStateEnum.REFLECT
            return TransitionResult(
                previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                new_state=str(SessionStateEnum.REFLECT),
                message_keys=["reflect_q"],
            )

        if prev == SessionStateEnum.REFLECT:
            ev = 3 if self.ctx.reflection_type == "peer" else 2
            self.ctx.evidence_level = max(self.ctx.evidence_level, ev)
            self.ctx.current_state = SessionStateEnum.DONE
            return TransitionResult(
                previous_state=str(SessionStateEnum.REFLECT),
                new_state=str(SessionStateEnum.DONE),
                message_keys=["week_done"],
                evidence_level=ev,
            )

        if prev == SessionStateEnum.DONE:
            if token in ("btn_next_move", "next_move", "अगला तरीका"):
                self.ctx.current_state = SessionStateEnum.LEARN
                self.ctx.rehearsal_turns_count = 0
                self.ctx.retries_count = 0
                return TransitionResult(
                    previous_state=str(SessionStateEnum.DONE),
                    new_state=str(SessionStateEnum.LEARN),
                    message_keys=["learn_intro"],
                )
            if token in ("btn_progress", "progress", "मेरी प्रगति"):
                return TransitionResult(
                    previous_state=str(SessionStateEnum.DONE),
                    new_state=str(SessionStateEnum.DONE),
                    message_keys=["progress_summary"],
                )

        return TransitionResult(
            previous_state=str(prev),
            new_state=str(self.ctx.current_state),
            message_keys=[],
        )


class OnboardingStateMachine:
    """Manages legal transitions in teacher onboarding (spec/08 §8.1)."""

    def __init__(self, context: SessionContext) -> None:
        self.ctx = context

    def get_state_prompt_key(self, state: OnboardingStateEnum | str | None = None) -> str:
        """Returns primary message prompt key for onboarding state (spec/08 §8.1)."""
        target = state if state is not None else self.ctx.onboarding_state
        return ONBOARDING_PROMPT_KEYS.get(str(target), "welcome")

    def transition(self, input_text_or_btn: str) -> TransitionResult:
        """Processes onboarding inputs and advances state (spec/08 §8.1)."""
        token = input_text_or_btn.strip().lower()
        prev = self.ctx.onboarding_state

        if prev == OnboardingStateEnum.NEW:
            if token in ("btn_agree", "agree", "सहमत हूँ", "yes", "हाँ"):
                self.ctx.onboarding_state = OnboardingStateEnum.JOIN_CODE
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.JOIN_CODE),
                    message_keys=["ask_join_code"],
                )
            if token in ("btn_more", "more", "और जानें"):
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.NEW),
                    message_keys=["consent_details"],
                )
            if token in ("btn_decline", "decline", "नहीं", "no"):
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.NEW),
                    message_keys=["consent_declined"],
                )

        if prev == OnboardingStateEnum.JOIN_CODE:
            if token in ("valid_code", "knp-c01-b1", "knp-c01-b2", "demo"):
                self.ctx.cluster_id = token.upper()
                self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_NAME
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.PROFILE_NAME),
                    message_keys=["ask_name"],
                )
            if token in ("no_code", "नहीं", "no", "skip"):
                self.ctx.cluster_id = "UNASSIGNED"
                self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_NAME
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.PROFILE_NAME),
                    message_keys=["ask_name"],
                )
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.JOIN_CODE),
                message_keys=["join_code_invalid"],
            )

        if prev == OnboardingStateEnum.PROFILE_NAME:
            self.ctx.name = input_text_or_btn[:40].strip()
            self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_ADDRESS
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PROFILE_ADDRESS),
                message_keys=["ask_address_form"],
            )

        if prev == OnboardingStateEnum.PROFILE_ADDRESS:
            if token in ("btn_male", "शिक्षक", "m"):
                self.ctx.address_form = "m"
            else:
                self.ctx.address_form = "f"
            self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_EXPERIENCE
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PROFILE_EXPERIENCE),
                message_keys=["ask_experience"],
            )

        if prev == OnboardingStateEnum.PROFILE_EXPERIENCE:
            self.ctx.experience_band = token
            self.ctx.first_year = "0-1" in token or "exp_0_1" in token
            self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_CLASSES
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PROFILE_CLASSES),
                message_keys=["ask_classes"],
            )

        if prev == OnboardingStateEnum.PROFILE_CLASSES:
            self.ctx.classes = [1, 2]
            self.ctx.onboarding_state = OnboardingStateEnum.SHARE_CONSENT
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.SHARE_CONSENT),
                message_keys=["consent_share_scores"],
            )

        if prev == OnboardingStateEnum.SHARE_CONSENT:
            self.ctx.onboarding_state = OnboardingStateEnum.PLACEMENT_INTRO
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PLACEMENT_INTRO),
                message_keys=["placement_intro"],
            )

        if prev == OnboardingStateEnum.PLACEMENT_INTRO:
            self.ctx.onboarding_state = OnboardingStateEnum.PLACEMENT
            self.ctx.placement_turns_count = 0
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PLACEMENT),
                message_keys=["placement_intro"],
            )

        if prev == OnboardingStateEnum.PLACEMENT:
            self.ctx.placement_turns_count += 1
            if self.ctx.placement_turns_count >= 2:
                self.ctx.onboarding_state = OnboardingStateEnum.READY
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.READY),
                    message_keys=["placement_done", "ready_first_move"],
                )
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PLACEMENT),
                message_keys=[],
            )

        if prev == OnboardingStateEnum.READY:
            self.ctx.onboarding_state = OnboardingStateEnum.READY
            self.ctx.current_state = SessionStateEnum.LEARN
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(SessionStateEnum.LEARN),
                message_keys=["learn_intro"],
            )

        return TransitionResult(
            previous_state=str(prev),
            new_state=str(self.ctx.onboarding_state),
            message_keys=[],
        )


def get_weekly_prompt_message_key(is_outside_24h: bool) -> str:
    """Returns template vs freeform message key depending on 24h window (spec/08 §8.6, §8.8)."""
    return "tpl_weekly_move" if is_outside_24h else "weekly_move"


__all__ = [
    "SessionStateEnum",
    "OnboardingStateEnum",
    "SessionContext",
    "WeeklyStateMachine",
    "OnboardingStateMachine",
    "TransitionResult",
    "TransitionEdge",
    "WEEKLY_LOOP_STATES",
    "STATE_PROMPT_KEYS",
    "ONBOARDING_PROMPT_KEYS",
    "STATE_TRANSITION_TABLE",
    "get_weekly_prompt_message_key",
]
