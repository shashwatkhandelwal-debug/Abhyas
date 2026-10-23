"""A move's title in the UI language, for every line that puts it inside a sentence."""

from __future__ import annotations

from backend.app.core.messages import get_message, has_message
from backend.app.rehearsal.scene_runner import load_move_card


def move_title(move_id: str) -> str:
    """The title for the current UI language: the catalogue's translation, else the card's Hindi one.

    A line in the English UI that names the move must not carry a Hindi title in the middle of an
    English sentence, so the English titles live in the catalogue (`move_title_<id>`).
    """
    key = f"move_title_{move_id}"
    if has_message(key):
        return get_message(key)
    try:
        return load_move_card(move_id).title_hi
    except FileNotFoundError:
        return move_id
