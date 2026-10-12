"""LLM roles module (spec/05)."""

from backend.app.llm.roles.act_tagger import fallback_tag_act, tag_act
from backend.app.llm.roles.child_voice import template_line, voice_child_line

__all__ = ["fallback_tag_act", "tag_act", "template_line", "voice_child_line"]
