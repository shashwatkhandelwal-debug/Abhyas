"""Content validator enforcing spec/10 §10.3 checks (1, 2, 5, 6, 7)."""

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from backend.app.content_models import MoveCard, PersonaCard

# Valid Teaching Acts taxonomy (spec/04 §4.3)
TEACHING_ACTS_TAXONOMY = {
    "ask_to_explain",
    "concrete_representation",
    "probe_simpler_case",
    "phonics_sound_out",
    "contrast_answers",
    "model_step_aloud",
    "involve_peer",
    "tell_answer",
    "repeat_question",
    "praise_effort",
    "praise_generic",
    "scold",
    "off_task",
    "give_new_problem",
}

# Known Bug Rules Registry IDs (all 12 from spec/04 §4.2)
BUG_REGISTRY_IDS = {
    # Subtraction
    "SUB_SMALLER_FROM_LARGER",
    "SUB_BORROW_NO_DECREMENT",
    "SUB_WRITE_ZERO_WHEN_STUCK",
    # Addition
    "ADD_NO_CARRY",
    "ADD_CARRY_FORGOTTEN",
    "ADD_CARRY_WRONG_DIGIT",
    # Place Value
    "PV_BUNDLE_AS_ONE",
    "PV_CONCAT_SPOKEN",
    "PV_REVERSAL",
    # Literacy
    "MATRA_DROP",
    "FIRST_AKSHAR_GUESS",
    "AKSHAR_BY_AKSHAR",
}

DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")


class ContentValidationError(Exception):
    """Raised when content validation fails."""

    pass


def is_nfc(text: str) -> bool:
    return text == unicodedata.normalize("NFC", text)


def has_devanagari(text: str) -> bool:
    return bool(DEVANAGARI_REGEX.search(text))


def validate_move(
    move_data: dict[str, Any],
    sources_manifest: set[str],
    known_personas: set[str],
) -> MoveCard:
    """Validates a move card against checks 1, 2, 5, 6, 7 in spec/10 §10.3."""
    # Check 1: Schema validation
    try:
        move = MoveCard.model_validate(move_data)
    except Exception as e:
        raise ContentValidationError(f"Schema validation failed: {e}") from e

    # Check 1: Hindi fields NFC and no Latin-only _hi fields
    hi_fields = [
        ("title_hi", move.title_hi),
        ("summary_hi", move.summary_hi),
        ("learn_script_hi", move.learn_script_hi),
        ("scenario.intro_hi", move.scenario.intro_hi),
    ]
    for name, val in hi_fields:
        if not is_nfc(val):
            raise ContentValidationError(f"Field '{name}' is not NFC-normalized")
        if not has_devanagari(val):
            raise ContentValidationError(f"Field '{name}' must contain Devanagari text")

    for idx, kp in enumerate(move.key_points):
        if not is_nfc(kp.text_hi):
            raise ContentValidationError(f"Key point {idx} text_hi is not NFC-normalized")
        if not has_devanagari(kp.text_hi):
            raise ContentValidationError(f"Key point {idx} text_hi must contain Devanagari text")

    # Check 2: Acts and causes taxonomy checks
    for act in move.teaching_acts_effective:
        if act not in TEACHING_ACTS_TAXONOMY:
            raise ContentValidationError(f"Teaching act '{act}' not in taxonomy")

    for cause in move.target_causes:
        if cause not in BUG_REGISTRY_IDS:
            raise ContentValidationError(f"Target cause '{cause}' not in bug registry")

    for child in move.scenario.children:
        if child.misconception not in move.target_causes:
            raise ContentValidationError(
                f"Child {child.persona_id} misconception '{child.misconception}' not in move target_causes"
            )
        if child.persona_id not in known_personas:
            raise ContentValidationError(f"Child persona '{child.persona_id}' does not exist")

    # Check 5: Rubric checks
    criteria_count = len(move.rubric.criteria)
    if not (3 <= criteria_count <= 5):
        raise ContentValidationError(f"Rubric criteria count must be 3-5, got {criteria_count}")

    rubric_ids = set()
    for crit in move.rubric.criteria:
        rubric_ids.add(crit.id)
        if set(crit.levels.keys()) != {0, 1, 2}:
            raise ContentValidationError(f"Criterion '{crit.id}' must have levels 0, 1, and 2")
        for sa in crit.signal_acts:
            allowed_signals = set(move.teaching_acts_effective) | {"praise_effort", "involve_peer"}
            if sa not in allowed_signals:
                raise ContentValidationError(
                    f"Signal act '{sa}' in criterion '{crit.id}' not allowed"
                )
        for na in crit.negative_acts:
            if na not in TEACHING_ACTS_TAXONOMY:
                raise ContentValidationError(
                    f"Negative act '{na}' in criterion '{crit.id}' not in taxonomy"
                )

    for crit_id in rubric_ids:
        if crit_id not in move.feedback_bank:
            raise ContentValidationError(f"Feedback bank missing criterion '{crit_id}'")

    # Check 6: Learn script word count & key points
    learn_words = len(move.learn_script_hi.split())
    if not (100 <= learn_words <= 300):
        raise ContentValidationError(
            f"Learn script word count must be 100-300 words (≤ 2 min spoken), got {learn_words}"
        )

    kp_count = len(move.key_points)
    if not (4 <= kp_count <= 6):
        raise ContentValidationError(f"Key points count must be 4-6, got {kp_count}")

    must_have_count = sum(1 for kp in move.key_points if kp.must_have)
    if must_have_count < 2:
        raise ContentValidationError(
            f"Must have at least 2 must_have key points, got {must_have_count}"
        )

    # Check 7: module_ref.source_id exists in sources.yaml
    if move.module_ref.source_id not in sources_manifest:
        raise ContentValidationError(
            f"Module reference source_id '{move.module_ref.source_id}' not found in sources manifest"
        )

    return move


def validate_move_card(move_data: dict[str, Any]) -> MoveCard:
    """Helper alias for validating a move card with default manifests."""
    sources_manifest = {
        "nipun_guidelines_2021",
        "up_ganit_sandarshika_c1",
        "up_bhasha_sandarshika_c1",
        "ncert_vidya_pravesh",
        "nishtha_fln",
    }
    known_personas = {"ravi", "priya", "aman"}
    return validate_move(move_data, sources_manifest, known_personas)


def validate_all_content(content_dir: Path) -> list[MoveCard]:
    """Validates all move and persona files in content directory."""
    sources_path = content_dir / "sources" / "sources.yaml"
    with open(sources_path, encoding="utf-8") as f:
        sources_list = yaml.safe_load(f)
    sources_manifest = {s["id"] for s in sources_list}

    personas_dir = content_dir / "personas"
    known_personas = set()
    for persona_file in personas_dir.glob("*.yaml"):
        with open(persona_file, encoding="utf-8") as f:
            p_data = yaml.safe_load(f)
        p = PersonaCard.model_validate(p_data)
        known_personas.add(p.id)

    validated_moves = []
    moves_dir = content_dir / "moves"
    for move_file in moves_dir.glob("*.yaml"):
        with open(move_file, encoding="utf-8") as f:
            m_data = yaml.safe_load(f)
        validated_moves.append(validate_move(m_data, sources_manifest, known_personas))

    return validated_moves


if __name__ == "__main__":
    validated = validate_all_content(Path("content"))
    print(f"All {len(validated)} seed moves validated successfully!")
