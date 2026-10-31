"""English pronouns for the simulated children, from the rule data (config), never guessed from a name."""

from __future__ import annotations

from backend.app.config import settings

_FORMS: dict[str, tuple[str, str, str]] = {
    "he": ("he", "him", "his"),
    "she": ("she", "her", "her"),
}
_NEUTRAL = ("they", "them", "their")


def child_pronouns(persona_id: str | None) -> dict[str, str]:
    """Message kwargs `he`, `him`, `his` for a child; "they/them/their" only for an unknown child."""
    he, him, his = _FORMS.get(settings.CHILD_PRONOUN_EN.get(str(persona_id), ""), _NEUTRAL)
    return {"he": he, "him": him, "his": his}


__all__ = ["child_pronouns"]
