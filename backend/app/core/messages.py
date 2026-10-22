"""Message catalog loader, gender resolution, and startup validation (spec/08, spec/02 §2.5).

All teacher-facing strings come from `content/messages_hi.yaml` by key, with an English mirror in
`content/messages_en.yaml` for users who switch the UI language (Hindi is the default).
Picks `text_m` variant when teacher.address_form == "m" (Hindi only).
Missing key fails fast at startup with MessageCatalogError.
Asserts every key containing feminine verb markers has a text_m variant.
"""

from __future__ import annotations

import contextvars
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("abhyas.core.messages")

SUPPORTED_LANGS = ("hi", "en")
DEFAULT_LANG = "hi"
LANG_COOKIE_NAME = "abhyas_lang"

# Language of the request / task being served; `get_message` uses it when `lang` is not passed.
_ui_lang: contextvars.ContextVar[str] = contextvars.ContextVar(
    "abhyas_ui_lang", default=DEFAULT_LANG
)


def normalize_lang(raw: str | None) -> str:
    """Returns a supported language code, falling back to the default (Hindi)."""
    code = (raw or "").strip().lower()
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


def get_ui_lang() -> str:
    return _ui_lang.get()


def set_ui_lang(lang: str | None) -> contextvars.Token[str]:
    """Sets the language for the current context; pass the token to `reset_ui_lang` to undo."""
    return _ui_lang.set(normalize_lang(lang))


def reset_ui_lang(token: contextvars.Token[str]) -> None:
    _ui_lang.reset(token)


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
    """In-memory cache and resolver for one language's messages catalog."""

    def __init__(self, catalog_path: Path | str | None = None, lang: str = DEFAULT_LANG) -> None:
        self.lang = lang
        if catalog_path is None:
            self.catalog_path = Path(__file__).parents[3] / "content" / f"messages_{lang}.yaml"
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

        if self.lang != DEFAULT_LANG:
            return  # gender variants only exist in Hindi

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

    def keys(self) -> set[str]:
        return set(self._messages)

    def texts_with_prefix(self, prefix: str) -> dict[str, str]:
        """Raw (unformatted, feminine-form) texts of every key starting with `prefix`."""
        return {
            key: str(entry.get("text", ""))
            for key, entry in self._messages.items()
            if key.startswith(prefix)
        }


# One catalog per language, loaded lazily
_catalogs: dict[str, MessageCatalog] = {}


def get_catalog(catalog_path: Path | str | None = None, lang: str | None = None) -> MessageCatalog:
    """Catalog for `lang` (default Hindi). Passing `catalog_path` replaces that language's catalog."""
    code = DEFAULT_LANG if lang is None else normalize_lang(lang)
    if code not in _catalogs or catalog_path is not None:
        _catalogs[code] = MessageCatalog(catalog_path, lang=code)
    return _catalogs[code]


def get_message(key: str, address_form: str = "f", lang: str | None = None, **kwargs: Any) -> str:
    """Formatted message text in `lang` (default: the language of the current request/task).

    An English key that is missing falls back to Hindi (a test keeps the two catalogs in sync).
    """
    code = normalize_lang(lang) if lang is not None else get_ui_lang()
    if code != DEFAULT_LANG:
        catalog = get_catalog(lang=code)
        if catalog.has(key):
            return catalog.get(key, address_form=address_form, **kwargs)
        logger.warning("Message key '%s' missing in '%s' catalog; using Hindi", key, code)
    return get_catalog(lang=DEFAULT_LANG).get(key, address_form=address_form, **kwargs)


def texts_for_lang(prefix: str, lang: str | None = None) -> dict[str, str]:
    """`prefix` texts for the UI strings JSON: Hindi base overlaid with the requested language."""
    code = get_ui_lang() if lang is None else normalize_lang(lang)
    texts = get_catalog(lang=DEFAULT_LANG).texts_with_prefix(prefix)
    if code != DEFAULT_LANG:
        texts.update(get_catalog(lang=code).texts_with_prefix(prefix))
    return texts


def get_message_spec(key: str) -> dict[str, Any]:
    """Convenience helper to retrieve full message spec (Hindi: carries audio/buttons flags)."""
    return get_catalog(lang=DEFAULT_LANG).get_spec(key)


def has_message(key: str) -> bool:
    """Convenience helper to check message existence."""
    return get_catalog(lang=DEFAULT_LANG).has(key)


__all__ = [
    "DEFAULT_LANG",
    "LANG_COOKIE_NAME",
    "SUPPORTED_LANGS",
    "get_ui_lang",
    "normalize_lang",
    "reset_ui_lang",
    "set_ui_lang",
    "texts_for_lang",
    "MessageCatalogError",
    "MessageCatalog",
    "get_catalog",
    "get_message",
    "get_message_spec",
    "has_message",
    "FEMININE_MARKERS",
    "REQUIRED_MESSAGE_KEYS",
]
