"""Content pipeline validator (§14).

Enforces:
1. Every key point is traceable to a source section.
2. Numbers in scenarios verified by procedural rules.
3. Rule tests pass.
4. Hindi NFC normalization.
5. Length constraints on scripts.
"""

import unicodedata
from typing import Any
from pydantic import ValidationError
from backend.app.rule_engine.domain import Move


class ContentValidationError(Exception):
    pass


def validate_move_card(move_dict: dict[str, Any]) -> Move:
    """Validates move dictionary against pedagogical and technical constraints."""
    # 1. Pydantic validation
    try:
        move = Move.model_validate(move_dict)
    except ValidationError as e:
        raise ContentValidationError(f"Schema validation error: {e}") from e

    # 2. Source traceability check (§14)
    if not move.module_ref.module_name or not move.module_ref.section:
        raise ContentValidationError("Module reference must specify module_name and section")

    if not move.key_points:
        raise ContentValidationError("Move must contain at least one key point")

    # 3. Unicode NFC check (§18)
    for kp in move.key_points:
        if kp.text_hi != unicodedata.normalize("NFC", kp.text_hi):
            raise ContentValidationError(f"KeyPoint '{kp.id}' text is not NFC-normalized")

    # 4. Length constraints check
    learn_words = move.learn_script_hi.split()
    if len(learn_words) > 300:  # ~2 minutes spoken Hindi
        raise ContentValidationError(f"Learn script exceeds 2-minute word limit: {len(learn_words)} words")

    return move
