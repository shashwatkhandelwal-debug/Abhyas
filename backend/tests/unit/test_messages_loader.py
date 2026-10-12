"""Unit tests for centralized message catalog loader (backend/app/llm/messages.py)."""

from __future__ import annotations

import pytest

from backend.app.llm.messages import (
    clear_catalog_cache,
    load_catalog_message,
)


def test_load_catalog_message_default_feminine() -> None:
    """Loads default message text when address_form is 'f'."""
    clear_catalog_cache()
    msg = load_catalog_message("btn_understood", address_form="f")
    assert msg == "समझ गई, आगे"


def test_load_catalog_message_masculine_variant() -> None:
    """Loads masculine text_m variant when address_form is 'm'."""
    clear_catalog_cache()
    msg = load_catalog_message("btn_understood", address_form="m")
    assert msg == "समझ गया, आगे"


def test_load_catalog_message_with_kwargs_formatting() -> None:
    """Correctly substitutes format placeholders."""
    clear_catalog_cache()
    msg = load_catalog_message(
        "fidelity_reply_summary",
        n_covered=2,
        n_total=3,
    )
    assert msg == "धन्यवाद! आपने 2 में से 3 मुख्य बातें कहीं।"


def test_load_catalog_message_missing_key_raises_key_error() -> None:
    """Raises KeyError when message key does not exist."""
    clear_catalog_cache()
    with pytest.raises(KeyError, match="Missing message key"):
        load_catalog_message("non_existent_key_12345")
