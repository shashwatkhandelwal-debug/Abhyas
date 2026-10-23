"""Unit tests for centralized message catalog loader (backend/app/llm/messages.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.llm.messages import (
    clear_catalog_cache,
    load_catalog_message,
)

HI_CATALOG = Path(__file__).resolve().parents[3] / "content" / "messages_hi.yaml"


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


def _hindi_catalog() -> dict[str, dict[str, object]]:
    import yaml

    raw = yaml.safe_load(HI_CATALOG.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def test_every_hindi_key_with_a_feminine_verb_has_a_masculine_variant() -> None:
    """The catalogue loader only logs a warning for a missing text_m; this makes it a failure."""
    import re

    from backend.app.core.messages import FEMININE_MARKERS

    missing = [
        key
        for key, entry in _hindi_catalog().items()
        if isinstance(entry.get("text"), str)
        and any(re.search(marker, str(entry["text"])) for marker in FEMININE_MARKERS)
        and "text_m" not in entry
    ]
    assert missing == []


def test_masculine_variants_are_nfc_and_a_changed_variant_has_no_feminine_verbs() -> None:
    import re
    import unicodedata

    from backend.app.core.messages import FEMININE_MARKERS

    for key, entry in _hindi_catalog().items():
        male = entry.get("text_m")
        if male is None:
            continue
        assert isinstance(male, str) and unicodedata.is_normalized("NFC", male), key
        if male == entry["text"]:
            continue  # same sentence for every reader: the verb agrees with a feminine noun
        assert not any(re.search(marker, male) for marker in FEMININE_MARKERS), key


def test_the_seven_keys_that_used_to_warn_now_have_masculine_text() -> None:
    from backend.app.core.messages import get_message

    for key in (
        "ask_out_of_scope",
        "unsupported_type",
        "unclear",
        "ui_chat_source_ocr",
        "ui_delete_question",
        "ui_progress_data_desc",
        "ui_chat_help_text",
    ):
        assert get_message(key, "m", lang="hi")
    assert "सकता हूँ" in get_message("ask_out_of_scope", "m", lang="hi")
    assert "समझ नहीं पाया" in get_message("unclear", "m", lang="hi")
    assert "चाहते हैं" in get_message("ui_delete_question", "m", lang="hi")


def test_loading_the_hindi_catalogue_logs_no_missing_variant_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from backend.app.core.messages import MessageCatalog

    with caplog.at_level(logging.WARNING, logger="abhyas.core.messages"):
        MessageCatalog(HI_CATALOG, lang="hi")
    assert "missing text_m" not in caplog.text
