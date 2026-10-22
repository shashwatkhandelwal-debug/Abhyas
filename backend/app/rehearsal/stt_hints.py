"""STT spelling hints for rehearsal scenes: the scene's child names (रवि, प्रिया, अमन...).

Hints only: they are passed to the provider as keyterms / spelling hints. The transcript is
never post-edited, guessed or auto-corrected against them.
"""

from __future__ import annotations

import logging
import unicodedata
from functools import lru_cache
from uuid import UUID

from backend.app.content_models import PersonaCard
from backend.app.rehearsal.scene_store import scene_store

logger = logging.getLogger("abhyas.rehearsal.stt_hints")


@lru_cache(maxsize=1)
def _personas() -> dict[str, PersonaCard]:
    from backend.app.rehearsal.scene_runner import load_personas

    return load_personas()


async def scene_child_name_hints(teacher_id: UUID) -> list[str]:
    """Hindi names of the children in the teacher's active scene ([] when there is none)."""
    try:
        scene = await scene_store.get_active_for_teacher(teacher_id)
    except Exception as exc:  # hints are an optimisation, never a reason to fail a voice note
        logger.warning("stt hint lookup failed for teacher %s: %s", teacher_id, exc)
        return []
    if scene is None or not scene.active:
        return []
    personas = _personas()
    names: list[str] = []
    for child in scene.scene_state.children:
        persona = personas.get(child.persona_id)
        if persona is not None:
            names.append(unicodedata.normalize("NFC", persona.name_hi))
    return names
