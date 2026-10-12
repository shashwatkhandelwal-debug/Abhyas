"""LLM roles module (spec/05)."""

from backend.app.llm.roles.act_tagger import fallback_tag_act, tag_act
from backend.app.llm.roles.child_voice import template_line, voice_child_line
from backend.app.llm.roles.coach import CoachResult, coach_feedback, fallback_coach_feedback
from backend.app.llm.roles.fidelity_checker import (
    FidelityResult,
    check_fidelity,
    compose_fidelity_reply,
    fallback_fidelity,
)

__all__ = [
    "CoachResult",
    "FidelityResult",
    "check_fidelity",
    "coach_feedback",
    "compose_fidelity_reply",
    "fallback_coach_feedback",
    "fallback_fidelity",
    "fallback_tag_act",
    "tag_act",
    "template_line",
    "voice_child_line",
]
