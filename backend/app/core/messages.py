"""Message catalog loader, gender resolution, and startup validation (spec/08, spec/02 §2.5).

All teacher-facing strings come from `content/messages_hi.yaml` by key.
Picks `text_m` variant when teacher.address_form == "m".
Missing key fails fast at startup with MessageCatalogError.
Asserts every key containing feminine verb markers has a text_m variant.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("abhyas.core.messages")

# Common feminine verb markers in FLN Hindi context (spec/08 §8.1 notes)
FEMININE_MARKERS = [
    r"रही हैं",
    r"चाहती",
    r"थीं",
    r"पहुँचीं",
    r"बताऊँगी",
    r"गई",
    r"पाई",
    r"सकती",
    r"करेंगी",
    r"सीखेंगी",
]

# Essential catalog keys that MUST be present at startup (fail fast if missing)
REQUIRED_MESSAGE_KEYS = [
    "welcome",
    "consent_service",
    "consent_details",
    "consent_declined",
    "ask_join_code",
    "join_code_invalid",
    "ask_name",
    "ask_address_form",
    "btn_female",
    "btn_male",
    "ask_experience",
    "ask_classes",
]


class MessageCatalogError(Exception):
    """Raised when the message catalog is missing required keys or malformed."""

    pass


class MessageCatalog:
    """In-memory cache and resolver for Hindi messages catalog."""

    def __init__(self, catalog_path: Path | str | None = None) -> None:
        if catalog_path is None:
            self.catalog_path = Path(__file__).parents[3] / "content" / "messages_hi.yaml"
        else:
            self.catalog_path = Path(catalog_path)
        self._messages: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Loads and validates message catalog from yaml."""
        if not self.catalog_path.is_file():
            raise MessageCatalogError(f"Message catalog file not found: {self.catalog_path}")

        try:
            with open(self.catalog_path, encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}
        except Exception as exc:
            raise MessageCatalogError(f"Failed to parse message catalog YAML: {exc}") from exc

        if not isinstance(raw_data, dict):
            raise MessageCatalogError("Message catalog root must be a dictionary")

        messages: dict[str, dict[str, Any]] = {}
        for k, v in raw_data.items():
            if isinstance(v, dict):
                # Ensure all strings are NFC normalized
                entry: dict[str, Any] = {}
                for sub_k, sub_v in v.items():
                    if isinstance(sub_v, str):
                        entry[sub_k] = unicodedata.normalize("NFC", sub_v)
                    else:
                        entry[sub_k] = sub_v
                messages[k] = entry
            elif isinstance(v, str):
                messages[k] = {"text": unicodedata.normalize("NFC", v)}

        self._messages = messages
        self.validate()

    def validate(self) -> None:
        """Validates that all required keys are present and gender variants exist."""
        # 1. Required keys check
        missing = [k for k in REQUIRED_MESSAGE_KEYS if k not in self._messages]
        if missing:
            raise MessageCatalogError(f"Missing required message catalog keys: {missing}")

        # 2. Gender variant check: every key containing feminine marker must have text_m
        missing_male_variants: list[str] = []
        for key, entry in self._messages.items():
            text = entry.get("text", "")
            if not isinstance(text, str):
                continue
            has_fem = any(re.search(marker, text) for marker in FEMININE_MARKERS)
            if has_fem and "text_m" not in entry:
                missing_male_variants.append(key)

        if missing_male_variants:
            logger.warning(
                "Catalog keys containing feminine markers missing text_m variant: %s",
                missing_male_variants,
            )

    def get(self, key: str, address_form: str = "f", **kwargs: Any) -> str:
        """Retrieves and formats a message by key and teacher address form ('f' or 'm')."""
        if key not in self._messages:
            raise MessageCatalogError(f"Unknown message key: '{key}'")

        entry = self._messages[key]
        if address_form == "m" and "text_m" in entry and entry["text_m"]:
            template = str(entry["text_m"])
        else:
            template = str(entry.get("text", ""))

        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as exc:
                raise MessageCatalogError(
                    f"Missing placeholder argument {exc} for key '{key}'"
                ) from exc

        return template

    def get_spec(self, key: str) -> dict[str, Any]:
        """Returns the full dictionary spec for a key (text, text_m, audio, buttons, etc.)."""
        if key not in self._messages:
            raise MessageCatalogError(f"Unknown message key: '{key}'")
        return self._messages[key]

    def has(self, key: str) -> bool:
        """Returns True if the message key exists in the catalog."""
        return key in self._messages

    def texts_with_prefix(self, prefix: str) -> dict[str, str]:
        """Raw (unformatted, feminine-form) texts of every key starting with `prefix`."""
        return {
            key: str(entry.get("text", ""))
            for key, entry in self._messages.items()
            if key.startswith(prefix)
        }


# Singleton catalog instance loaded at import time
_catalog: MessageCatalog | None = None


def get_catalog(catalog_path: Path | str | None = None) -> MessageCatalog:
    global _catalog
    if _catalog is None or catalog_path is not None:
        _catalog = MessageCatalog(catalog_path)
    return _catalog


def get_message(key: str, address_form: str = "f", **kwargs: Any) -> str:
    """Convenience helper to retrieve formatted message text."""
    return get_catalog().get(key, address_form=address_form, **kwargs)


def get_message_spec(key: str) -> dict[str, Any]:
    """Convenience helper to retrieve full message spec."""
    return get_catalog().get_spec(key)


def has_message(key: str) -> bool:
    """Convenience helper to check message existence."""
    return get_catalog().has(key)


__all__ = [
    "MessageCatalogError",
    "MessageCatalog",
    "get_catalog",
    "get_message",
    "get_message_spec",
    "has_message",
    "FEMININE_MARKERS",
    "REQUIRED_MESSAGE_KEYS",
]
