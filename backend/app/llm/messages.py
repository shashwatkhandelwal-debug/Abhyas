"""Centralized message catalog loader for teacher-facing messages (spec/08, T14).

Loads messages from content/messages_hi.yaml with NFC normalization, caching,
and gender-variant support (address_form = 'f' | 'm').
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("abhyas.llm.messages")

_MESSAGES_CACHE: dict[str, Any] | None = None
_MESSAGES_FILE_PATH: Path | None = None


def _find_messages_file() -> Path:
    """Finds content/messages_hi.yaml by searching up directory hierarchy."""
    global _MESSAGES_FILE_PATH
    if _MESSAGES_FILE_PATH is not None and _MESSAGES_FILE_PATH.is_file():
        return _MESSAGES_FILE_PATH

    curr = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = curr / "content" / "messages_hi.yaml"
        if candidate.is_file():
            _MESSAGES_FILE_PATH = candidate
            return candidate
        curr = curr.parent

    fallback = Path("content/messages_hi.yaml").resolve()
    _MESSAGES_FILE_PATH = fallback
    return fallback


def _get_catalog_data() -> dict[str, Any]:
    """Loads and caches YAML catalog data."""
    global _MESSAGES_CACHE
    if _MESSAGES_CACHE is not None:
        return _MESSAGES_CACHE

    path = _find_messages_file()
    if not path.is_file():
        raise FileNotFoundError(f"Message catalog not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Catalog at {path} did not parse to a dictionary")
        _MESSAGES_CACHE = data
        return data


def clear_catalog_cache() -> None:
    """Clears cached catalog data (for tests)."""
    global _MESSAGES_CACHE, _MESSAGES_FILE_PATH
    _MESSAGES_CACHE = None
    _MESSAGES_FILE_PATH = None


def load_catalog_message(key: str, address_form: str = "f", **kwargs: Any) -> str:
    """Loads, selects gender variant, formats, and NFC-normalizes a message from catalog.

    Args:
        key: Message key from messages_hi.yaml
        address_form: 'f' (default) or 'm' for teacher address form
        **kwargs: Format string placeholders to substitute

    Returns:
        NFC normalized formatted message string

    Raises:
        KeyError: If key is missing from catalog
        ValueError: If catalog entry is invalid or empty
    """
    data = _get_catalog_data()
    if key not in data:
        path = _find_messages_file()
        raise KeyError(f"Missing message key: '{key}' in {path}")

    entry = data[key]
    if not isinstance(entry, dict) or "text" not in entry or not entry["text"]:
        raise ValueError(f"Invalid or empty message entry for key: '{key}'")

    raw_text: str
    if address_form == "m" and "text_m" in entry and entry["text_m"]:
        raw_text = str(entry["text_m"])
    else:
        raw_text = str(entry["text"])

    if kwargs:
        raw_text = raw_text.format(**kwargs)

    return unicodedata.normalize("NFC", raw_text)


__all__ = [
    "clear_catalog_cache",
    "load_catalog_message",
]
