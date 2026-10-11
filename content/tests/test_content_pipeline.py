"""Tests for content validation rules (spec/10 §10.3 checks 1, 2, 5, 6, 7)."""

from pathlib import Path

import pytest
import yaml

from content.pipeline.validator import (
    ContentValidationError,
    validate_all_content,
    validate_move,
)


@pytest.fixture
def sources_and_personas() -> tuple[set[str], set[str]]:
    sources_path = Path("content/sources/sources.yaml")
    with open(sources_path, encoding="utf-8") as f:
        sources_list = yaml.safe_load(f)
    sources = {s["id"] for s in sources_list}

    personas = {"ravi", "priya", "aman"}
    return sources, personas


def test_seed_moves_pass_all_checks() -> None:
    """All 4 seed moves must pass checks 1, 2, 5, 6, 7 cleanly."""
    validated = validate_all_content(Path("content"))
    assert len(validated) == 4
    ids = {m.id for m in validated}
    assert "NUM_SUB_REGROUP_BUNDLES" in ids
    assert "NUM_ADD_CARRY_BUNDLES" in ids
    assert "NUM_PLACE_VALUE_BUNDLES" in ids
    assert "LIT_MATRA_BLENDING" in ids


def test_check1_fails_on_non_nfc_or_latin_only(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 1: Fails if Hindi fields are Latin-only."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    broken_move["title_hi"] = "Substraction with bundles"  # Latin only!
    with pytest.raises(ContentValidationError, match="Devanagari"):
        validate_move(broken_move, sources, personas)


def test_check2_fails_on_unknown_teaching_act(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 2: Fails if teaching act is not in taxonomy."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    broken_move["teaching_acts_effective"] = ["ask_to_explain", "invented_act_outside_taxonomy"]
    with pytest.raises(ContentValidationError, match="taxonomy"):
        validate_move(broken_move, sources, personas)


def test_check2_fails_on_unknown_child_misconception(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 2: Fails if child misconception is not in move target_causes."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    broken_move["scenario"]["children"][0]["misconception"] = "NON_EXISTENT_BUG"
    with pytest.raises(ContentValidationError, match="target_causes"):
        validate_move(broken_move, sources, personas)


def test_check5_fails_on_missing_rubric_levels(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 5: Fails if rubric criterion does not have levels 0, 1, 2."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    broken_move["rubric"]["criteria"][0]["levels"] = {0: "zero", 1: "one"}  # missing level 2
    with pytest.raises(ContentValidationError, match="levels 0, 1, and 2"):
        validate_move(broken_move, sources, personas)


def test_check5_fails_on_missing_feedback_bank(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 5: Fails if feedback_bank lacks criterion."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    del broken_move["feedback_bank"]["crit_explain"]
    with pytest.raises(ContentValidationError, match="Feedback bank missing"):
        validate_move(broken_move, sources, personas)


def test_check6_fails_on_learn_script_word_count(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 6: Fails if learn script is too short (< 100 words)."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    broken_move["learn_script_hi"] = "यह बहुत छोटा पाठ है।"
    with pytest.raises(ContentValidationError, match="word count"):
        validate_move(broken_move, sources, personas)


def test_check6_fails_on_insufficient_must_have_key_points(
    sources_and_personas: tuple[set[str], set[str]],
) -> None:
    """Check 6: Fails if fewer than 2 must_have key points."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    for kp in broken_move["key_points"]:
        kp["must_have"] = False
    with pytest.raises(ContentValidationError, match="must_have"):
        validate_move(broken_move, sources, personas)


def test_check7_fails_on_missing_source_id(sources_and_personas: tuple[set[str], set[str]]) -> None:
    """Check 7: Fails if module_ref source_id does not exist in sources manifest."""
    sources, personas = sources_and_personas
    with open("content/moves/NUM_SUB_REGROUP_BUNDLES.yaml", encoding="utf-8") as f:
        broken_move = yaml.safe_load(f)

    broken_move["module_ref"]["source_id"] = "non_existent_source_manifest_id"
    with pytest.raises(ContentValidationError, match="sources manifest"):
        validate_move(broken_move, sources, personas)
