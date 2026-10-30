"""Is this line a question to the app ("what do I do now?") and not something said to a child?

A small deterministic matcher: no LLM. It only says yes when the whole line is one of a short list
of help phrases (Hindi, romanised Hindi, English; typos tolerated) and nothing in it addresses a
child, contains a number, or sounds like an instruction to a child. When unsure it says no, so a
real teaching line always goes on to the scene.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from backend.app.config import settings

_PUNCT = re.compile(r"[\s.,!?;:।॥'\"‘’“”()\[\]\-_/\\|~`*]+")
_DIGITS = re.compile(r"[0-9०-९]")

# Names of the simulated children in Devanagari and Latin script (any form that starts with one)
_CHILD_NAMES = ("रवि", "प्रिया", "अमन", "ravi", "priya", "aman")
# Words that turn a line into an instruction or question to a child, or into a teaching prompt
_CHILD_FORMS = (
    "करोगे",
    "करोगी",
    "करो",
    "karoge",
    "karogi",
    "karo",
    "घटाओ",
    "जोड़ो",
    "पढ़ो",
    "लिखो",
    "बताओ",
    "बोलो",
    "सुनाओ",
    "बनाओ",
    "ghatao",
    "jodo",
    "padho",
    "likho",
    "batao",
    "bolo",
    "tum",
    "तुम",
    "तुमने",
)

HELP_PHRASES = (
    # Hindi
    "अब क्या करें",
    "अब क्या करूँ",
    "अब क्या करना है",
    "क्या करना है",
    "मुझे क्या करना है",
    "आगे क्या",
    "आगे क्या करें",
    "आगे क्या करना है",
    "मदद",
    "मदद चाहिए",
    "मुझे मदद चाहिए",
    "समझ नहीं आया क्या करूँ",
    "समझ नहीं आया क्या करें",
    "यह कैसे काम करता है",
    "अब क्या",
    # romanised Hindi
    "ab kya karein",
    "ab kya kare",
    "ab kya karun",
    "ab kya karna hai",
    "kya karna hai",
    "mujhe kya karna hai",
    "aage kya",
    "aage kya karein",
    "aage kya karna hai",
    "madad",
    "madad chahiye",
    "samajh nahi aaya kya karun",
    "samajh nahi aaya kya karein",
    "ye kaise kaam karta hai",
    # English
    "help",
    "help me",
    "what now",
    "what should i do",
    "what should i do now",
    "what should i do next",
    "what do i do",
    "what do i do now",
    "what next",
    "what to do now",
    "what to do next",
    "how does this work",
    "how do i use this",
    "i need help",
)


def _fold(text: str) -> str:
    """NFC, lower case, no punctuation, chandrabindu and nukta folded (करूँ == करूं == करून)."""
    s = unicodedata.normalize("NFC", text or "").lower()
    s = s.replace("ँ", "ं").replace("़", "")
    s = _PUNCT.sub(" ", s)
    return " ".join(s.split())


_FOLDED = tuple(dict.fromkeys(_fold(p) for p in HELP_PHRASES))


def addresses_child_or_teaches(text: str) -> bool:
    words = _fold(text).split()
    if _DIGITS.search(text or ""):
        return True
    for w in words:
        if any(w.startswith(_fold(n)) for n in _CHILD_NAMES):
            return True
        if w in {_fold(f) for f in _CHILD_FORMS}:
            return True
    return False


def is_help_question(text: str | None) -> bool:
    """True only for a clear question to the app about the next step."""
    if not text:
        return False
    folded = _fold(text)
    if not folded or len(folded.split()) > settings.HELP_QUESTION_MAX_WORDS:
        return False
    if addresses_child_or_teaches(text):
        return False
    if folded in _FOLDED:
        return True
    return any(
        SequenceMatcher(None, folded, phrase).ratio() >= settings.HELP_QUESTION_MIN_SIMILARITY
        for phrase in _FOLDED
    )


__all__ = ["HELP_PHRASES", "addresses_child_or_teaches", "is_help_question"]
