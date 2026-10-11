"""LLM prompt templates export."""

from backend.app.llm.prompts.act_tagger import ACT_TAGGER_SYSTEM_PROMPT
from backend.app.llm.prompts.child_voice import CHILD_VOICE_SYSTEM_PROMPT
from backend.app.llm.prompts.coach import COACH_SYSTEM_PROMPT
from backend.app.llm.prompts.fidelity_checker import FIDELITY_CHECKER_SYSTEM_PROMPT
from backend.app.llm.prompts.guide_answerer import GUIDE_ANSWERER_SYSTEM_PROMPT

__all__ = [
    "ACT_TAGGER_SYSTEM_PROMPT",
    "CHILD_VOICE_SYSTEM_PROMPT",
    "COACH_SYSTEM_PROMPT",
    "FIDELITY_CHECKER_SYSTEM_PROMPT",
    "GUIDE_ANSWERER_SYSTEM_PROMPT",
]
