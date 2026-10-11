"""Devanagari Akshar splitter matching spec/04 §4.2.

Pure Python deterministic implementation without relying on regex `\\X`.
An akshar = (independent vowel | consonant [+ nukta] (+ virama + consonant [+ nukta])*)
             + optional dependent vowel sign
             + optional (ं|ँ|ः)
"""

import re
import unicodedata

# Devanagari character class definitions
_INDEPENDENT_VOWELS = r"[\u0904-\u0914\u0960\u0961\u0972\u0976\u0977]"
_CONSONANTS = r"[\u0915-\u0939\u0958-\u095F]"
_NUKTA = r"\u093C"
_VIRAMA = r"\u094D"
_CONSONANT_WITH_NUKTA = rf"{_CONSONANTS}{_NUKTA}?"
_CONJUNCT = rf"{_CONSONANT_WITH_NUKTA}(?:{_VIRAMA}[\u200C\u200D]?{_CONSONANT_WITH_NUKTA})*"
_BASE = rf"(?:{_INDEPENDENT_VOWELS}|{_CONJUNCT})"
_MATRA = r"[\u093E-\u094C\u094E\u094F\u0955-\u0957\u0962\u0963]"
_MODIFIERS = r"[\u0901-\u0903]"

_AKSHAR_RE = re.compile(rf"{_BASE}{_MATRA}?{_MODIFIERS}?")


def split_akshars(text: str) -> list[str]:
    """Splits a Devanagari word/text into individual aksharas.

    Tested on:
    - किताब -> ['कि', 'ता', 'ब']
    - गुड़िया -> ['गु', 'ड़ि', 'या']
    - विद्यालय -> ['वि', 'द्या', 'ल', 'य']
    - आम -> ['आ', 'म']
    - संतरा -> ['सं', 'त', 'रा']
    """
    if not text:
        return []
    norm_text = unicodedata.normalize("NFC", text.strip())
    # Find all akshar matches
    matches = _AKSHAR_RE.findall(norm_text)
    return matches


def join_akshars(akshars: list[str], sep: str = " - ") -> str:
    """Joins aksharas with separator, used for AKSHAR_BY_AKSHAR reading bug."""
    return sep.join(akshars)


def strip_matras(text: str) -> str:
    """Drops all dependent vowel signs (matras) and modifiers (ं ँ ः).

    Used for MATRA_DROP bug.
    """
    norm_text = unicodedata.normalize("NFC", text.strip())
    # Strip matras and anusvara/candrabindu/visarga
    drop_pattern = re.compile(rf"{_MATRA}|{_MODIFIERS}")
    return drop_pattern.sub("", norm_text)
