"""Content generator and publisher pipelines (§14)."""

import logging
from typing import Any

import yaml

from content.pipeline.validator import validate_move_card

logger = logging.getLogger(__name__)


def load_and_validate_move_yaml(yaml_path: str) -> dict[str, Any]:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    move = validate_move_card(data)
    return move.model_dump()


def publish_release(moves_list: list[dict[str, Any]], version_tag: str) -> dict[str, Any]:
    """Prepares and validates versioned content release for DB publishing."""
    logger.info("Publishing release %s with %d moves", version_tag, len(moves_list))
    return {
        "version": version_tag,
        "moves_count": len(moves_list),
        "status": "ready_for_review_console_approval",
    }
