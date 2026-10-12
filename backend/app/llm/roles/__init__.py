"""LLM roles module (spec/05)."""

from backend.app.llm.roles.act_tagger import fallback_tag_act, tag_act
from backend.app.llm.roles.child_voice import template_line, voice_child_line
from backend.app.llm.roles.coach import CoachResult, coach_feedback, fallback_coach_feedback

__all__ = [
    "CoachResult",
    "coach_feedback",
    "fallback_coach_feedback",
    "fallback_tag_act",
    "tag_act",
    "template_line",
    "voice_child_line",
]
