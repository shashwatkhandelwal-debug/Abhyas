"""Session State Machine for the Weekly Loop and Onboarding (spec/08 §8.1–§8.4, T20)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.core.intents import (
    BUTTON_INTENT_MAP,
    Intent,
    match_intent,
)
from backend.app.core.messages import get_message, get_ui_lang
from backend.app.core.name_extract import extract_name


class SessionStateEnum(StrEnum):
    """Weekly loop session states (spec/08 §8.2)."""

    LEARN = "LEARN"
    EXPLAIN_BACK = "EXPLAIN_BACK"
    MODEL = "MODEL"
    REHEARSE_INTRO = "REHEARSE_INTRO"
    REHEARSE = "REHEARSE"
    FEEDBACK = "FEEDBACK"
    TRY_IN_CLASS = "TRY_IN_CLASS"
    REFLECT_PEER = "REFLECT_PEER"
    REFLECT_SELF = "REFLECT_SELF"
    DONE = "DONE"
    ASK = "ASK"  # Interruption state (spec/08 §8.4)


WEEKLY_LOOP_STATES: tuple[SessionStateEnum, ...] = (
    SessionStateEnum.LEARN,
    SessionStateEnum.EXPLAIN_BACK,
    SessionStateEnum.MODEL,
    SessionStateEnum.REHEARSE_INTRO,
    SessionStateEnum.REHEARSE,
    SessionStateEnum.FEEDBACK,
    SessionStateEnum.TRY_IN_CLASS,
    SessionStateEnum.REFLECT_PEER,
    SessionStateEnum.REFLECT_SELF,
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
    SessionStateEnum.REHEARSE_INTRO: "rehearse_intro",
    SessionStateEnum.REHEARSE: "rehearse_intro",
    SessionStateEnum.FEEDBACK: "feedback_header",
    SessionStateEnum.TRY_IN_CLASS: "try_in_class",
    SessionStateEnum.REFLECT_PEER: "peer_item",
    SessionStateEnum.REFLECT_SELF: "reflect_q",
    SessionStateEnum.DONE: "week_done",
    SessionStateEnum.ASK: "ask_prompt",
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
        description="Teacher selects female honorific",
    ),
    TransitionEdge(
        source_state="PROFILE_ADDRESS",
        input_kind="btn_male",
        target_state="PROFILE_EXPERIENCE",
        message_keys=("ask_experience",),
        description="Teacher selects male honorific",
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
        target_state="PLACEMENT_INTRO",
        message_keys=("placement_intro",),
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
        source_state="LEARN",
        input_kind="free_text",
        target_state="LEARN",
        message_keys=(),
        description="Free text does not advance LEARN state silently",
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
        target_state="REHEARSE_INTRO",
        message_keys=("model_header", "rehearse_intro"),
        description="Teacher listens to model teacher rehearsal",
    ),
    TransitionEdge(
        source_state="MODEL",
        input_kind="btn_skip",
        target_state="REHEARSE_INTRO",
        message_keys=("rehearse_intro",),
        description="Teacher skips model audio and goes to rehearsal intro",
    ),
    TransitionEdge(
        source_state="MODEL",
        input_kind="free_text",
        target_state="MODEL",
        message_keys=(),
        description="Free text does not advance MODEL state silently",
    ),
    TransitionEdge(
        source_state="REHEARSE_INTRO",
        input_kind="start_turn",
        target_state="REHEARSE",
        message_keys=(),
        description="First voice/text starts active deliberate practice rehearsal",
    ),
    TransitionEdge(
        source_state="REHEARSE",
        input_kind="teacher_turn",
        target_state="REHEARSE",
        message_keys=(),
        description="Teacher executes deliberate practice turn",
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
        target_state="REHEARSE_INTRO",
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
        source_state="TRY_IN_CLASS",
        input_kind="btn_peer",
        target_state="REFLECT_PEER",
        message_keys=("peer_item",),
        description="Teacher selects peer observation reflection path",
    ),
    TransitionEdge(
        source_state="TRY_IN_CLASS",
        input_kind="btn_self",
        target_state="REFLECT_SELF",
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
        source_state="TRY_IN_CLASS",
        input_kind="free_text",
        target_state="TRY_IN_CLASS",
        message_keys=(),
        description="Free text does not advance TRY_IN_CLASS state silently",
    ),
    TransitionEdge(
        source_state="REFLECT_PEER",
        input_kind="checklist_item",
        target_state="REFLECT_PEER",
        message_keys=("peer_item",),
        description="Teacher answers a checklist item",
    ),
    TransitionEdge(
        source_state="REFLECT_PEER",
        input_kind="checklist_done",
        target_state="DONE",
        message_keys=("week_done",),
        description="Teacher finishes peer checklist, reaching evidence level 3",
    ),
    TransitionEdge(
        source_state="REFLECT_SELF",
        input_kind="q1_answer",
        target_state="REFLECT_SELF",
        message_keys=("reflect_q",),
        description="Teacher answers reflection question 1",
    ),
    TransitionEdge(
        source_state="REFLECT_SELF",
        input_kind="q2_answer",
        target_state="DONE",
        message_keys=("week_done",),
        description="Teacher answers reflection question 2, reaching evidence level 2",
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
    TransitionEdge(
        source_state="DONE",
        input_kind="free_text",
        target_state="DONE",
        message_keys=(),
        description="Free text does not advance DONE state silently",
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
        target_state="LEARN",
        message_keys=("delete_confirm",),
        description="Teacher triggers delete data flow with confirmation prompt",
    ),
    TransitionEdge(
        source_state="LEARN",
        input_kind="confirm_delete",
        target_state="NEW",
        message_keys=("data_deleted",),
        description="Teacher confirms data deletion, resetting to NEW",
    ),
    TransitionEdge(
        source_state="LEARN",
        input_kind="cancel_delete",
        target_state="LEARN",
        message_keys=("learn_intro",),
        description="Teacher cancels data deletion, resuming previous state",
    ),
)


class TransitionResult(BaseModel):
    """Result of a state transition."""

    previous_state: str
    new_state: str
    message_keys: list[str] = Field(default_factory=list)
    evidence_level: int | None = None
    resumed: bool = False
    needs_intent_router: bool = False
    rehearsal_ended: bool = False


class SessionContext(BaseModel):
    """Context state tracking weekly deliberative practice loop and onboarding (spec/08)."""

    teacher_id: str
    week_start: str
    current_move_id: str
    current_state: SessionStateEnum = SessionStateEnum.LEARN
    prior_state_before_ask: SessionStateEnum | None = None
    prior_state_before_delete: SessionStateEnum | None = None
    awaiting_delete_confirm: bool = False
    onboarding_state: OnboardingStateEnum = OnboardingStateEnum.NEW
    retries_count: int = 0
    rehearsal_turns_count: int = 0
    placement_turns_count: int = 0
    reflection_type: str | None = None  # "self" or "peer"
    reflect_step: int = 0
    peer_checklist_total: int = 3
    evidence_level: int = 0
    child_states: dict[str, int] = Field(default_factory=dict)
    last_inbound_at: datetime | None = None
    lite_mode: bool = False
    address_form: str = "f"
    name: str | None = None
    cluster_id: str | None = None
    batch_id: str | None = None
    district: str | None = None
    experience_band: str | None = None
    first_year: bool = False
    classes: list[int] = Field(default_factory=list)
    consent_service: bool = False
    consent_share_scores: bool = False
    asked_share_consent: bool = False
    clarifying_already_asked: bool = False
    # "Rate the training" after REFLECT: "" (not asking), "rating" (waiting for 1-5), "comment"
    rating_stage: str = ""
    # One-on-one rehearsal setup (see sessions/rehearse_setup.py)
    rehearse_stage: str = ""  # "", choose_mode, choose_child, diagnose, scene
    rehearse_mode: str = ""  # "", one_on_one, group
    rehearse_child: str = ""  # persona id of the 1-1 child
    diagnosis: dict[str, Any] = Field(default_factory=dict)  # DiagnosisResult + "skipped"
    module_mode: bool = False  # the week was started from the module picker
    module_check_stage: str = ""  # "", asking, done (the closing check question)
    # "My class" (class_profile/flow.py): "" (not asking), "asking" (waiting for her words or a chip),
    # "confirm" (waiting for yes / change on `class_pending`)
    class_stage: str = ""
    class_pending: list[str] = Field(default_factory=list)
    class_struggles: list[str] = Field(
        default_factory=list
    )  # saved choice, mirrors the teacher row
    # "What do you want to get better at?" (class_profile/skills_flow.py): "" (not asking),
    # "asking" (waiting for her words, a chip or a number), "confirm" (yes / change on `skill_pending`)
    skill_stage: str = ""
    skill_pending: list[str] = Field(default_factory=list)
    teaching_skills: list[str] = Field(
        default_factory=list
    )  # saved choice, mirrors the teacher row
    # "After class: how did it go?" (class_profile/checkin_flow.py): "" (not in it), "module",
    # "outcome", "struggle", "result"; the rest is what she has tapped so far (closed-list ids only)
    checkin_stage: str = ""
    checkin_module: str = ""
    checkin_outcome: str = ""
    checkin_struggle: str = ""
    checkin_page: int = 0
    checkin_jump_move: str = ""  # a move opened from a check-in: its learn step was skipped
    # Follow-up loop (class_profile/followup.py): the open follow-up row and where she is in it
    followup_id: str = ""
    followup_stage: str = ""  # "", "ask", "why"
    scene_line_at: str = ""  # ISO time of her last line sent to a scene ("" if none)
    # "Group my class by level" (class_profile/level_sorter.py): "" (not in it), "subject", "count",
    # "result"; the tapped range per level is kept for this conversation only (never stored)
    level_stage: str = ""
    level_subject: str = ""
    level_idx: int = 0
    level_counts: dict[str, str] = Field(default_factory=dict)
    rating_unclear: int = 0  # unclear replies to the 1-5 prompt so far
    rating_level: int = 0  # evidence level reached, kept for the week_done message afterwards
    resume_scene_id: str = (
        ""  # a scene ended too early for feedback; "Continue the scene" reopens it
    )


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
        return diff > 86400

    def is_inactive_resume(self) -> bool:
        """Checks if teacher was inactive > 6 h in a mid-week state (spec/08 §8.2)."""
        if not self.ctx.last_inbound_at:
            return False
        if self.ctx.current_state in (SessionStateEnum.DONE, SessionStateEnum.LEARN):
            return False
        now = datetime.now(UTC)
        diff = (now - self.ctx.last_inbound_at).total_seconds()
        return diff > 21600

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
        self.ctx.clarifying_already_asked = False
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
            SessionStateEnum.LEARN: SessionStateEnum.EXPLAIN_BACK,
            SessionStateEnum.EXPLAIN_BACK: SessionStateEnum.MODEL,
            SessionStateEnum.MODEL: SessionStateEnum.REHEARSE_INTRO,
            SessionStateEnum.REHEARSE_INTRO: SessionStateEnum.REHEARSE,
            SessionStateEnum.REHEARSE: SessionStateEnum.FEEDBACK,
            SessionStateEnum.FEEDBACK: SessionStateEnum.TRY_IN_CLASS,
            SessionStateEnum.TRY_IN_CLASS: SessionStateEnum.REFLECT_SELF,
            SessionStateEnum.REFLECT_SELF: SessionStateEnum.DONE,
            SessionStateEnum.REFLECT_PEER: SessionStateEnum.DONE,
        }
        if self.ctx.current_state in transitions:
            self.ctx.current_state = transitions[self.ctx.current_state]
        return self.ctx.current_state

    def reset(self) -> None:
        """Resets teacher session data to initial state (spec/08 §8.3)."""
        self.ctx.current_state = SessionStateEnum.LEARN
        self.ctx.prior_state_before_ask = None
        self.ctx.prior_state_before_delete = None
        self.ctx.awaiting_delete_confirm = False
        self.ctx.onboarding_state = OnboardingStateEnum.NEW
        self.ctx.retries_count = 0
        self.ctx.rehearsal_turns_count = 0
        self.ctx.placement_turns_count = 0
        self.ctx.reflection_type = None
        self.ctx.reflect_step = 0
        self.ctx.evidence_level = 0
        self.ctx.child_states = {}
        self.ctx.name = None
        self.ctx.cluster_id = None
        self.ctx.batch_id = None
        self.ctx.district = None
        self.ctx.experience_band = None
        self.ctx.first_year = False
        self.ctx.classes = []
        self.ctx.consent_service = False
        self.ctx.consent_share_scores = False
        self.ctx.clarifying_already_asked = False

    def transition(
        self,
        input_text_or_btn: str = "",
        intent: Intent | str | None = None,
        button_id: str | None = None,
        scene_ended: bool = False,
    ) -> TransitionResult:
        """Processes input or intent against the weekly state machine using match_intent (spec/08 §8.2–§8.4)."""
        raw_text = input_text_or_btn.strip()
        prev = self.ctx.current_state

        # Determine canonical Intent via match_intent
        matched_intent: Intent | None = None
        if isinstance(intent, Intent):
            matched_intent = intent
        elif isinstance(intent, str):
            matched_intent = match_intent(text=intent, button_id=intent)

        if matched_intent is None:
            in_rehearsal_mode = prev == SessionStateEnum.REHEARSE
            matched_intent = match_intent(
                text=raw_text,
                in_rehearsal=in_rehearsal_mode,
                button_id=button_id or (raw_text if raw_text in BUTTON_INTENT_MAP else None),
            )

        # 1. Delete confirmation handling (§8.3 step 7)
        if self.ctx.awaiting_delete_confirm:
            if (
                matched_intent in (Intent.CONFIRM_DELETE, Intent.CONFIRM_YES)
                or raw_text == "confirm_delete"
                or button_id == "btn_delete_confirm"
            ):
                self.ctx.awaiting_delete_confirm = False
                self.reset()
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.NEW),
                    message_keys=["data_deleted"],
                )
            elif (
                matched_intent in (Intent.CANCEL_DELETE, Intent.CONFIRM_NO)
                or raw_text == "cancel_delete"
                or button_id in ("btn_delete_cancel", "btn_no")
            ):
                self.ctx.awaiting_delete_confirm = False
                target = self.ctx.prior_state_before_delete or SessionStateEnum.LEARN
                self.ctx.current_state = target
                self.ctx.prior_state_before_delete = None
                prompt_key = self.get_state_prompt_key(target)
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(target),
                    message_keys=[prompt_key],
                    resumed=True,
                )
            else:
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(prev),
                    message_keys=["delete_confirm"],
                )

        # 2. Global Intents (§8.3)
        if matched_intent == Intent.HELP or raw_text == "help":
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=["help_menu"],
            )

        if matched_intent == Intent.LITE_TOGGLE or raw_text == "lite_toggle":
            self.ctx.lite_mode = not self.ctx.lite_mode
            key = "lite_on" if self.ctx.lite_mode else "lite_off"
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=[key],
            )

        if matched_intent == Intent.PROGRESS or raw_text in ("progress", "btn_progress"):
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=["progress_summary"],
            )

        if matched_intent == Intent.DELETE or raw_text == "delete":
            self.ctx.awaiting_delete_confirm = True
            self.ctx.prior_state_before_delete = prev
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(prev),
                message_keys=["delete_confirm"],
            )

        if matched_intent == Intent.ASK or raw_text in ("ask", "btn_ask"):
            self.handle_ask_interruption()
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(SessionStateEnum.ASK),
                message_keys=["ask_prompt"],
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

        # 3. State-specific transitions (§8.2)
        if prev == SessionStateEnum.LEARN:
            if matched_intent == Intent.REPEAT or raw_text == "btn_replay":
                return TransitionResult(
                    previous_state=str(SessionStateEnum.LEARN),
                    new_state=str(SessionStateEnum.LEARN),
                    message_keys=["learn_intro"],
                )
            if matched_intent == Intent.NEXT or raw_text == "btn_understood":
                self.ctx.current_state = SessionStateEnum.EXPLAIN_BACK
                return TransitionResult(
                    previous_state=str(SessionStateEnum.LEARN),
                    new_state=str(SessionStateEnum.EXPLAIN_BACK),
                    message_keys=["explain_back_prompt"],
                )
            # Free text does not advance LEARN state silently (§8.3 step 4)
            return TransitionResult(
                previous_state=str(SessionStateEnum.LEARN),
                new_state=str(SessionStateEnum.LEARN),
                message_keys=[],
                needs_intent_router=True,
            )

        if prev == SessionStateEnum.EXPLAIN_BACK:
            self.ctx.current_state = SessionStateEnum.MODEL
            if matched_intent == Intent.SKIP or raw_text == "btn_skip":
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
            if matched_intent == Intent.LISTEN or raw_text in ("btn_listen", "listen"):
                self.ctx.current_state = SessionStateEnum.REHEARSE_INTRO
                return TransitionResult(
                    previous_state=str(SessionStateEnum.MODEL),
                    new_state=str(SessionStateEnum.REHEARSE_INTRO),
                    message_keys=["model_header", "rehearse_intro"],
                )
            if matched_intent == Intent.SKIP or raw_text in ("btn_skip", "skip"):
                self.ctx.current_state = SessionStateEnum.REHEARSE_INTRO
                return TransitionResult(
                    previous_state=str(SessionStateEnum.MODEL),
                    new_state=str(SessionStateEnum.REHEARSE_INTRO),
                    message_keys=["rehearse_intro"],
                )
            # Free text does not advance MODEL state silently (§8.3 step 4)
            return TransitionResult(
                previous_state=str(SessionStateEnum.MODEL),
                new_state=str(SessionStateEnum.MODEL),
                message_keys=[],
                needs_intent_router=True,
            )

        if prev == SessionStateEnum.REHEARSE_INTRO:
            self.ctx.current_state = SessionStateEnum.REHEARSE
            self.ctx.rehearsal_turns_count = 1
            return TransitionResult(
                previous_state=str(SessionStateEnum.REHEARSE_INTRO),
                new_state=str(SessionStateEnum.REHEARSE),
                message_keys=[],
            )

        if prev == SessionStateEnum.REHEARSE:
            if matched_intent == Intent.STOP_SCENE or scene_ended or raw_text == "stop_scene":
                self.ctx.current_state = SessionStateEnum.FEEDBACK
                ev = 1 if self.ctx.rehearsal_turns_count >= 3 else 0
                if ev > 0:
                    self.ctx.evidence_level = max(self.ctx.evidence_level, 1)
                return TransitionResult(
                    previous_state=str(SessionStateEnum.REHEARSE),
                    new_state=str(SessionStateEnum.FEEDBACK),
                    message_keys=["feedback_header", "realism_prompt"],
                    evidence_level=ev,
                    rehearsal_ended=True,
                )
            # Active rehearsal turn
            self.ctx.rehearsal_turns_count += 1
            return TransitionResult(
                previous_state=str(SessionStateEnum.REHEARSE),
                new_state=str(SessionStateEnum.REHEARSE),
                message_keys=[],
            )

        if prev == SessionStateEnum.FEEDBACK:
            if matched_intent == Intent.RETRY or raw_text == "btn_retry":
                if self.can_retry_rehearsal():
                    self.ctx.retries_count += 1
                    self.ctx.current_state = SessionStateEnum.REHEARSE_INTRO
                    return TransitionResult(
                        previous_state=str(SessionStateEnum.FEEDBACK),
                        new_state=str(SessionStateEnum.REHEARSE_INTRO),
                        message_keys=["rehearse_intro"],
                    )
                self.ctx.current_state = SessionStateEnum.TRY_IN_CLASS
                return TransitionResult(
                    previous_state=str(SessionStateEnum.FEEDBACK),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["retry_limit", "try_in_class"],
                )
            if raw_text == "retry_limit_reached":
                self.ctx.current_state = SessionStateEnum.TRY_IN_CLASS
                return TransitionResult(
                    previous_state=str(SessionStateEnum.FEEDBACK),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["retry_limit", "try_in_class"],
                )
            if matched_intent == Intent.NEXT or raw_text == "btn_continue":
                self.ctx.current_state = SessionStateEnum.TRY_IN_CLASS
                return TransitionResult(
                    previous_state=str(SessionStateEnum.FEEDBACK),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["try_in_class"],
                )
            # Realism rating or free feedback input stays in FEEDBACK
            return TransitionResult(
                previous_state=str(SessionStateEnum.FEEDBACK),
                new_state=str(SessionStateEnum.FEEDBACK),
                message_keys=[],
            )

        if prev == SessionStateEnum.TRY_IN_CLASS:
            if matched_intent == Intent.PEER or raw_text == "btn_peer":
                self.ctx.reflection_type = "peer"
                self.ctx.reflect_step = 1
                self.ctx.current_state = SessionStateEnum.REFLECT_PEER
                return TransitionResult(
                    previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                    new_state=str(SessionStateEnum.REFLECT_PEER),
                    message_keys=["peer_item"],
                )
            if matched_intent == Intent.SELF or raw_text == "btn_self":
                self.ctx.reflection_type = "self"
                self.ctx.reflect_step = 1
                self.ctx.current_state = SessionStateEnum.REFLECT_SELF
                return TransitionResult(
                    previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                    new_state=str(SessionStateEnum.REFLECT_SELF),
                    message_keys=["reflect_q"],
                )
            if matched_intent == Intent.LATER or raw_text == "btn_later":
                return TransitionResult(
                    previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                    new_state=str(SessionStateEnum.TRY_IN_CLASS),
                    message_keys=["reminder"],
                )
            # Free text does not advance TRY_IN_CLASS state silently (§8.3 step 4)
            return TransitionResult(
                previous_state=str(SessionStateEnum.TRY_IN_CLASS),
                new_state=str(SessionStateEnum.TRY_IN_CLASS),
                message_keys=[],
                needs_intent_router=True,
            )

        if prev == SessionStateEnum.REFLECT_PEER:
            if (
                raw_text == "checklist_done"
                or self.ctx.reflect_step >= self.ctx.peer_checklist_total
            ):
                self.ctx.evidence_level = max(self.ctx.evidence_level, 3)
                self.ctx.current_state = SessionStateEnum.DONE
                return TransitionResult(
                    previous_state=str(SessionStateEnum.REFLECT_PEER),
                    new_state=str(SessionStateEnum.DONE),
                    message_keys=["week_done"],
                    evidence_level=3,
                )
            self.ctx.reflect_step += 1
            return TransitionResult(
                previous_state=str(SessionStateEnum.REFLECT_PEER),
                new_state=str(SessionStateEnum.REFLECT_PEER),
                message_keys=["peer_item"],
            )

        if prev == SessionStateEnum.REFLECT_SELF:
            if raw_text in ("q2_answer", "reflection_done") or self.ctx.reflect_step >= 2:
                self.ctx.evidence_level = max(self.ctx.evidence_level, 2)
                self.ctx.current_state = SessionStateEnum.DONE
                return TransitionResult(
                    previous_state=str(SessionStateEnum.REFLECT_SELF),
                    new_state=str(SessionStateEnum.DONE),
                    message_keys=["week_done"],
                    evidence_level=2,
                )
            self.ctx.reflect_step += 1
            return TransitionResult(
                previous_state=str(SessionStateEnum.REFLECT_SELF),
                new_state=str(SessionStateEnum.REFLECT_SELF),
                message_keys=["reflect_q"],
            )

        if prev == SessionStateEnum.DONE:
            if matched_intent == Intent.NEXT or raw_text in ("btn_next_move", "next_move"):
                self.ctx.current_state = SessionStateEnum.LEARN
                self.ctx.rehearsal_turns_count = 0
                self.ctx.retries_count = 0
                self.ctx.reflect_step = 0
                return TransitionResult(
                    previous_state=str(SessionStateEnum.DONE),
                    new_state=str(SessionStateEnum.LEARN),
                    message_keys=["learn_intro"],
                )
            if raw_text in ("btn_progress", "progress"):
                return TransitionResult(
                    previous_state=str(SessionStateEnum.DONE),
                    new_state=str(SessionStateEnum.DONE),
                    message_keys=["progress_summary"],
                )
            # Free text does not advance DONE state silently (§8.3 step 4)
            return TransitionResult(
                previous_state=str(SessionStateEnum.DONE),
                new_state=str(SessionStateEnum.DONE),
                message_keys=[],
                needs_intent_router=True,
            )

        return TransitionResult(
            previous_state=str(prev),
            new_state=str(self.ctx.current_state),
            message_keys=[],
        )


_DEVANAGARI_DIGITS = {0x966 + i: str(i) for i in range(10)}  # U+0966..U+096F to 0..9


def experience_band_of(text: str) -> str | None:
    """Her free words about her teaching years ("2-5 years", "3 years", "10+", Devanagari digits)
    as one of the stored bands (the teacher table only accepts these); None without a number."""
    cleaned = text.translate(_DEVANAGARI_DIGITS).lower().replace("exp_", "").replace("_", "-")
    numbers = [int(n) for n in re.findall(r"\d+", cleaned)]
    if not numbers:
        return None
    years = max(numbers)
    if "+" in cleaned or years > 10:
        return "10+"
    if years <= 1:
        return "0-1"
    if years <= 5:
        return "2-5"
    return "6-10"


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
        raw_text = input_text_or_btn.strip()
        token = raw_text.lower()
        prev = self.ctx.onboarding_state
        intent = match_intent(
            text=raw_text, button_id=raw_text if raw_text in BUTTON_INTENT_MAP else None
        )

        if prev == OnboardingStateEnum.NEW:
            if intent == Intent.CONFIRM_YES or token in ("btn_agree", "agree"):
                self.ctx.consent_service = True
                self.ctx.onboarding_state = OnboardingStateEnum.JOIN_CODE
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.JOIN_CODE),
                    message_keys=["ask_join_code"],
                )
            if intent == Intent.MORE or token in ("btn_more", "more"):
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.NEW),
                    message_keys=["consent_details"],
                )
            if intent == Intent.CONFIRM_NO or token in ("btn_decline", "decline"):
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.NEW),
                    message_keys=["consent_declined"],
                )

        if prev == OnboardingStateEnum.JOIN_CODE:
            valid_codes = ("valid_code", "knp-c01-b1", "knp-c01-b2", "demo")
            if token in valid_codes:
                if not self.ctx.cluster_id or self.ctx.cluster_id == "UNASSIGNED":
                    self.ctx.cluster_id = (
                        "KNP-C01" if ("knp" in token or token == "valid_code") else "DEMO-C01"
                    )
                if not self.ctx.batch_id:
                    self.ctx.batch_id = (
                        "KNP-B1"
                        if ("b1" in token or token == "valid_code")
                        else ("KNP-B2" if "b2" in token else "DEMO-B1")
                    )
                if not self.ctx.district:
                    self.ctx.district = "Kanpur Nagar"
                self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_NAME
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.PROFILE_NAME),
                    message_keys=["ask_name"],
                )
            if intent == Intent.CONFIRM_NO or token in ("no_code", "skip"):
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
            name = extract_name(raw_text, get_ui_lang())
            if name is None:  # not plainly a name: ask again, store nothing
                return TransitionResult(
                    previous_state=str(prev),
                    new_state=str(OnboardingStateEnum.PROFILE_NAME),
                    message_keys=["ask_name_again"],
                )
            self.ctx.name = name
            self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_ADDRESS
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PROFILE_ADDRESS),
                message_keys=["ask_address_form"],
            )

        if prev == OnboardingStateEnum.PROFILE_ADDRESS:
            if token in ("btn_male", get_message("btn_male", "m"), "m"):
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
            band = experience_band_of(token if token.startswith("exp_") else raw_text)
            self.ctx.experience_band = band
            self.ctx.first_year = band == "0-1"
            self.ctx.onboarding_state = OnboardingStateEnum.PROFILE_CLASSES
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PROFILE_CLASSES),
                message_keys=["ask_classes"],
            )

        if prev == OnboardingStateEnum.PROFILE_CLASSES:
            self.ctx.classes = [1, 2]
            self.ctx.onboarding_state = OnboardingStateEnum.PLACEMENT_INTRO
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PLACEMENT_INTRO),
                message_keys=["placement_intro"],
            )

        if prev == OnboardingStateEnum.SHARE_CONSENT:
            if intent == Intent.CONFIRM_YES or token == "btn_yes":
                self.ctx.consent_share_scores = True
            else:
                self.ctx.consent_share_scores = False
            self.ctx.onboarding_state = OnboardingStateEnum.PLACEMENT_INTRO
            return TransitionResult(
                previous_state=str(prev),
                new_state=str(OnboardingStateEnum.PLACEMENT_INTRO),
                message_keys=["placement_intro"],
            )

        if prev == OnboardingStateEnum.PLACEMENT_INTRO:
            self.ctx.onboarding_state = OnboardingStateEnum.PLACEMENT
            self.ctx.placement_turns_count = 1
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
