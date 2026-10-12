"""LLM roles module (spec/05)."""

from backend.app.llm.roles.act_tagger import fallback_tag_act, tag_act

__all__ = ["fallback_tag_act", "tag_act"]
