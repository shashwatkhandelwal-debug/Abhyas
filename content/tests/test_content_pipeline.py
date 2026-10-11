"""Tests for content validation and move schema verification."""

import os
from content.pipeline.generator import load_and_validate_move_yaml


def test_load_and_validate_exemplar_move():
    move_yaml_path = os.path.join("content", "moves", "NUM_BUNDLES_PLACE_VALUE.yaml")
    assert os.path.exists(move_yaml_path)

    move_data = load_and_validate_move_yaml(move_yaml_path)
    assert move_data["id"] == "NUM_BUNDLES_PLACE_VALUE"
    assert move_data["domain"] == "numeracy"
    assert len(move_data["key_points"]) >= 4
    assert "SUB_SMALLER_FROM_LARGER" in move_data["target_causes"]
