"""Intent classification and keyword matching (spec/08 §8.3, CHANGES 254f622 Item 6).

Implements NFC-normalized, word-boundary, whole-message and prefix matching for
global intents and rehearsal stop commands per spec/08 §8.3.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from enum import StrEnum

logger = logging.getLogger("abhyas.core.intents")


class Intent(StrEnum):
    """Canonical system intents (spec/08 §8.3)."""

    HELP = "help"
    STOP_SCENE = "stop_scene"
    NEXT = "next"
    SKIP = "skip"
    REPEAT = "repeat"
    ASK = "ask"
    LITE_TOGGLE = "lite_toggle"
    PROGRESS = "progress"
    CONSENT = "consent"
    DELETE = "delete"
    GREETING = "greeting"
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"
    CONFIRM_DELETE = "confirm_delete"
    CANCEL_DELETE = "cancel_delete"
    RETRY = "retry"
    LISTEN = "listen"
    PEER = "peer"
    SELF = "self"
    LATER = "later"
    MORE = "more"
    ADMIN = "admin"


# Boundary regex for Devanagari (\u0900-\u097F) and Latin/alphanumeric words
_WB = r"(?<![\u0900-\u097Fa-zA-Z0-9_])"
_WBE = r"(?![\u0900-\u097Fa-zA-Z0-9_])"

# Button IDs mapped directly to intents (spec/08 §8.3 Rule 1)
BUTTON_INTENT_MAP: dict[str, Intent] = {
    "confirm_yes": Intent.CONFIRM_YES,
    "confirm_no": Intent.CONFIRM_NO,
    "btn_yes": Intent.CONFIRM_YES,
    "btn_no": Intent.CONFIRM_NO,
    "btn_retry_speak": Intent.CONFIRM_NO,
    "btn_agree": Intent.CONFIRM_YES,
    "btn_decline": Intent.CONFIRM_NO,
    "btn_more": Intent.MORE,
    "btn_understood": Intent.NEXT,
    "btn_replay": Intent.REPEAT,
    "btn_skip": Intent.SKIP,
    "btn_continue": Intent.NEXT,
    "btn_next_move": Intent.NEXT,
    "btn_progress": Intent.PROGRESS,
    "btn_ask": Intent.ASK,
    "btn_listen": Intent.LISTEN,
    "btn_retry": Intent.RETRY,
    "btn_peer": Intent.PEER,
    "btn_self": Intent.SELF,
    "btn_later": Intent.LATER,
    "btn_delete_confirm": Intent.CONFIRM_DELETE,
    "btn_delete_cancel": Intent.CANCEL_DELETE,
    "btn_confirm_ok": Intent.CONFIRM_YES,
    "btn_confirm_redo": Intent.CONFIRM_NO,
    "btn_restart": Intent.NEXT,
    "btn_not_now": Intent.CONFIRM_NO,
    "btn_lite": Intent.LITE_TOGGLE,
}

# Stop scene regex: whole message or explicit stop phrases (spec/08 §8.3 Rule 2)
# "बस", "बस, हो गया", "stop", "रुको" ARE stops.
# "बस एक बंडल खोलो" is NOT a stop ("बस" used as "only/just").
_STOP_EXACT_PATTERNS = [
    re.compile(r"^बस\s*[,।!]?\s*(हो\s*गया|करो|रहने\s*दो|इतना\s*ही|खत्म|समाप्त|अब)?$", re.IGNORECASE),
    re.compile(r"^बस\s*[,।!]?.*(खत्म|समाप्त|रोक)", re.IGNORECASE),
    re.compile(r"^(रुको|रुकिए|रुको\s*अब|रुको\s*बस)$", re.IGNORECASE),
    re.compile(r"^(खत्म|खत्म\s*करो|समाप्त)$", re.IGNORECASE),
    re.compile(r"^(stop|stop\s*now|stop\s*scene)$", re.IGNORECASE),
    re.compile(r"^bas(\s*[,!]?\s*(ho\s*gaya|khatam|rok))?$", re.IGNORECASE),
    re.compile(r"^(rok|roko)$", re.IGNORECASE),
]

_HELP_PATTERN = re.compile(
    rf"^{_WB}(मदद|help|menu|मेनू){_WBE}(\s+(चाहिए|karo|करो|menu))?$",
    re.IGNORECASE,
)

_NEXT_PATTERN = re.compile(
    rf"^{_WB}(आगे|अगला|अगली|शुरू|next|start|aage|shuru){_WBE}(\s+(बढ़ें|बढ़ें|करो|chalo))?$",
    re.IGNORECASE,
)

_SKIP_PATTERN = re.compile(
    rf"^{_WB}(छोड़ें|छोड़ें|छोड़ो|छोड़ो|skip|chhodo|chodo){_WBE}$",
    re.IGNORECASE,
)

_REPEAT_PATTERN = re.compile(
    rf"^{_WB}(फिर\s*से|दोबारा|repeat|phir\s*se|wapas){_WBE}(\s+(सुनें|सुनना|bologe))?$",
    re.IGNORECASE,
)

_ADMIN_PATTERN = re.compile(
    rf"^{_WB}(admin|व्यवस्थापक|प्रशासक){_WBE}([:\s\-\?].*|$)",
    re.IGNORECASE,
)

_ASK_PREFIX_PATTERN = re.compile(
    rf"^{_WB}(सवाल|प्रश्न|question|sawal){_WBE}([:\s\-\?].*|$)",
    re.IGNORECASE,
)

_LITE_TOGGLE_PATTERN = re.compile(
    rf"^{_WB}(लाइट\s*मोड|लाइट|lite\s*mode|lite){_WBE}$",
    re.IGNORECASE,
)

_PROGRESS_PATTERN = re.compile(
    rf"^{_WB}(मेरी\s*प्रगति|प्रगति|progress){_WBE}$",
    re.IGNORECASE,
)

_CONSENT_PATTERN = re.compile(
    rf"^{_WB}(सहमति|सहमति\s*बदलें|consent){_WBE}$",
    re.IGNORECASE,
)

_DELETE_PATTERN = re.compile(
    rf"^{_WB}(मेरा\s*डेटा\s*हटाएँ|मेरा\s*डाटा\s*हटाएं|मेरा\s*डेटा\s*हटाएं|मेरा\s*डाटा\s*हटाएँ|delete\s*my\s*data){_WBE}$",
    re.IGNORECASE,
)

_CONFIRM_DELETE_PATTERN = re.compile(
    rf"^{_WB}(हाँ\s*[,।]?\s*मिटाएँ|हाँ\s*[,।]?\s*मिटाएं|delete\s+confirm|yes\s+delete){_WBE}$",
    re.IGNORECASE,
)

_CANCEL_DELETE_PATTERN = re.compile(
    rf"^{_WB}(नहीं\s*[,।]?\s*मत\s*मिटाएँ|नहीं\s*[,।]?\s*रहने\s*दो|cancel\s+delete){_WBE}$",
    re.IGNORECASE,
)

_RETRY_PATTERN = re.compile(
    rf"^{_WB}(फिर\s*से\s*अभ्यास|retry|दोबारा\s*अभ्यास){_WBE}$",
    re.IGNORECASE,
)

_LISTEN_PATTERN = re.compile(
    rf"^{_WB}(सुनें|सुनो|listen){_WBE}$",
    re.IGNORECASE,
)

_PEER_PATTERN = re.compile(
    rf"^{_WB}(साथी\s*ने\s*देखा|peer){_WBE}$",
    re.IGNORECASE,
)

_SELF_PATTERN = re.compile(
    rf"^{_WB}(खुद\s*बताऊँगी|खुद\s*बताऊँगा|खुद\s*बताऊंगी|खुद\s*बताऊंगा|self){_WBE}$",
    re.IGNORECASE,
)

_LATER_PATTERN = re.compile(
    rf"^{_WB}(बाद\s*में|later){_WBE}$",
    re.IGNORECASE,
)

_MORE_PATTERN = re.compile(
    rf"^{_WB}(और\s*जानें|और\s*जाने|more){_WBE}$",
    re.IGNORECASE,
)

_CONFIRM_YES_PATTERN = re.compile(
    rf"^{_WB}(हाँ|हा|haan|yes|सही|सही\s*है|sahii?){_WBE}[.!]?$",
    re.IGNORECASE,
)

_CONFIRM_NO_PATTERN = re.compile(
    rf"^{_WB}(नहीं|नही|nahi|no|फिर\s*से\s*बोलूँगी|फिर\s*से\s*बोलूंगी|गलत){_WBE}[.!]?$",
    re.IGNORECASE,
)

_GREETING_PATTERN = re.compile(
    rf"^{_WB}(नमस्ते|नमस्कार|hello|hi|hey){_WBE}(\s+(जी|madam|sir))?[.!]?$",
    re.IGNORECASE,
)


# Rehearsal routing: a how-to question the teacher asks the *app* (not a line spoken to a child).
# It needs all three: question form, teacher speaking about herself/himself in the first person
# ("कैसे कराऊँ", "how do I"), and no address to a child (second person, or a leading child name).
_QUESTION_FORM = re.compile(
    rf"\?|{_WB}(कैसे|क्यों|कैसा|कौन\s*सा|क्या|kaise|kyun|kyon|how|why|which|what){_WBE}|"
    rf"{_WB}(तरीका|उपाय|सुझाव)\s*(क्या|बताइए|बताएं|बताएँ|बताओ){_WBE}",
    re.IGNORECASE,
)
_FIRST_PERSON_VERB = re.compile(
    r"[ऀ-ॿ]+(?:ऊँ|ऊं|ूँ|ूं)(?![ऀ-ॿ])|"
    rf"{_WB}(?:मैं|मेरे|मेरी|मेरा|main|mere|meri|mera){_WBE}|"
    rf"{_WB}(?:kar(?:a|aa|u|oo|v?a)un|karun|karoon|sikha(?:u|oo)n|samjha(?:u|oo)n|"
    rf"padha(?:u|oo)n|bata(?:u|oo)n|sambhal(?:u|oo)n|karwa(?:u|oo)n){_WBE}|"
    rf"{_WB}(?:how|what)\s+(?:do|can|should|could|would)\s+i{_WBE}|"
    rf"{_WB}(?:should|can|could)\s+i{_WBE}|"
    rf"{_WB}how\s+to{_WBE}",
    re.IGNORECASE,
)
_ADDRESSES_CHILD = re.compile(
    rf"{_WB}(?:तुम|तुमने|तुम्हें|तुम्हे|तुम्हारा|तुम्हारी|तुम्हारे|tum|tumne|tumhe|you|your){_WBE}|"
    rf"^\s*(?:रवि|प्रिया|अमन|ravi|priya|aman)\s*[,!:\-]",
    re.IGNORECASE,
)


def is_pedagogy_question_for_app(text: str) -> bool:
    """True if text is a first-person how-to question addressed to the app, not to a child."""
    cleaned = normalize_intent_text(text)
    if not cleaned or len(cleaned) < 8:
        return False
    return bool(
        _QUESTION_FORM.search(cleaned)
        and _FIRST_PERSON_VERB.search(cleaned)
        and not _ADDRESSES_CHILD.search(cleaned)
    )


def normalize_intent_text(text: str) -> str:
    """Normalizes text for intent matching (spec/08 §8.3).

    Applies Unicode NFC normalization, trims whitespace, and collapses spacing.
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text).strip()
    norm = re.sub(r"\s+", " ", norm)
    return norm


def match_intent(
    text: str | None = None,
    in_rehearsal: bool = False,
    button_id: str | None = None,
    ask_anywhere: bool = False,
) -> Intent | None:
    """Matches text and/or button_id to a canonical system Intent (spec/08 §8.3).

    Order of evaluation:
    1. Direct button id match.
    2. In rehearsal: check stop keywords.
    3. Global keywords: help, next, skip, repeat, ask, lite_toggle, progress, consent, delete.
    4. Confirmation / greeting matches.
    """
    # 1. Button ID match
    if button_id and button_id in BUTTON_INTENT_MAP:
        return BUTTON_INTENT_MAP[button_id]

    if not text:
        return None

    cleaned = normalize_intent_text(text)
    if not cleaned:
        return None

    if cleaned in BUTTON_INTENT_MAP:
        return BUTTON_INTENT_MAP[cleaned]

    # Strip trailing punctuation for clean matching
    cleaned_punct = re.sub(r"[\s।,!\.?]+$", "", cleaned)

    # 2. Rehearsal stop check (REHEARSE state only)
    if in_rehearsal:
        for pat in _STOP_EXACT_PATTERNS:
            if pat.match(cleaned) or pat.match(cleaned_punct):
                return Intent.STOP_SCENE

    # 3. Global keywords in priority order (spec/08 §8.3)
    if _HELP_PATTERN.match(cleaned) or _HELP_PATTERN.match(cleaned_punct):
        return Intent.HELP

    if _SKIP_PATTERN.match(cleaned) or _SKIP_PATTERN.match(cleaned_punct):
        return Intent.SKIP

    if _REPEAT_PATTERN.match(cleaned) or _REPEAT_PATTERN.match(cleaned_punct):
        return Intent.REPEAT

    if _ADMIN_PATTERN.match(cleaned):
        return Intent.ADMIN

    if _ASK_PREFIX_PATTERN.match(cleaned):
        return Intent.ASK

    if _LITE_TOGGLE_PATTERN.match(cleaned) or _LITE_TOGGLE_PATTERN.match(cleaned_punct):
        return Intent.LITE_TOGGLE

    if _PROGRESS_PATTERN.match(cleaned) or _PROGRESS_PATTERN.match(cleaned_punct):
        return Intent.PROGRESS

    if _CONSENT_PATTERN.match(cleaned) or _CONSENT_PATTERN.match(cleaned_punct):
        return Intent.CONSENT

    if _DELETE_PATTERN.match(cleaned) or _DELETE_PATTERN.match(cleaned_punct):
        return Intent.DELETE

    # Delete confirmations
    if _CONFIRM_DELETE_PATTERN.match(cleaned) or _CONFIRM_DELETE_PATTERN.match(cleaned_punct):
        return Intent.CONFIRM_DELETE

    if _CANCEL_DELETE_PATTERN.match(cleaned) or _CANCEL_DELETE_PATTERN.match(cleaned_punct):
        return Intent.CANCEL_DELETE

    # Activity/flow intents
    if _RETRY_PATTERN.match(cleaned) or _RETRY_PATTERN.match(cleaned_punct):
        return Intent.RETRY

    if _LISTEN_PATTERN.match(cleaned) or _LISTEN_PATTERN.match(cleaned_punct):
        return Intent.LISTEN

    if _PEER_PATTERN.match(cleaned) or _PEER_PATTERN.match(cleaned_punct):
        return Intent.PEER

    if _SELF_PATTERN.match(cleaned) or _SELF_PATTERN.match(cleaned_punct):
        return Intent.SELF

    if _LATER_PATTERN.match(cleaned) or _LATER_PATTERN.match(cleaned_punct):
        return Intent.LATER

    if _MORE_PATTERN.match(cleaned) or _MORE_PATTERN.match(cleaned_punct):
        return Intent.MORE

    if _NEXT_PATTERN.match(cleaned) or _NEXT_PATTERN.match(cleaned_punct):
        return Intent.NEXT

    # 4. Confirmation intents
    if _CONFIRM_YES_PATTERN.match(cleaned) or _CONFIRM_YES_PATTERN.match(cleaned_punct):
        return Intent.CONFIRM_YES

    if _CONFIRM_NO_PATTERN.match(cleaned) or _CONFIRM_NO_PATTERN.match(cleaned_punct):
        return Intent.CONFIRM_NO

    # 5. Greetings
    if _GREETING_PATTERN.match(cleaned) or _GREETING_PATTERN.match(cleaned_punct):
        return Intent.GREETING

    # 6. A how-to question to the app goes to the guide, not to the children (in a scene, or at any
    # step where free text is not her answer)
    if (in_rehearsal or ask_anywhere) and is_pedagogy_question_for_app(cleaned):
        return Intent.ASK

    return None


def extract_ask_query(text: str) -> str:
    """Extracts the underlying question after an ASK keyword prefix."""
    cleaned = normalize_intent_text(text)
    match = _ADMIN_PATTERN.match(cleaned) or _ASK_PREFIX_PATTERN.match(cleaned)
    if match:
        remainder = cleaned[match.end(1) :].strip()
        remainder = re.sub(r"^[:\s\-\?]+", "", remainder).strip()
        return remainder
    return cleaned


__all__ = [
    "Intent",
    "match_intent",
    "normalize_intent_text",
    "extract_ask_query",
    "is_pedagogy_question_for_app",
    "BUTTON_INTENT_MAP",
]
