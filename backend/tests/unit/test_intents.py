"""Unit tests for Intent classification and matching (spec/08 §8.3, CHANGES 254f622 Item 6)."""

from backend.app.core.intents import (
    Intent,
    extract_ask_query,
    match_intent,
    normalize_intent_text,
)


def test_intent_rehearsal_stop_matching() -> None:
    """Tests stop scene intent in and out of rehearsal."""
    # In rehearsal: "बस" and "बस, हो गया" ARE stops
    assert match_intent("बस", in_rehearsal=True) == Intent.STOP_SCENE
    assert match_intent("बस, हो गया", in_rehearsal=True) == Intent.STOP_SCENE
    assert match_intent("बस हो गया", in_rehearsal=True) == Intent.STOP_SCENE
    assert match_intent("रुको", in_rehearsal=True) == Intent.STOP_SCENE
    assert match_intent("खत्म", in_rehearsal=True) == Intent.STOP_SCENE
    assert match_intent("stop", in_rehearsal=True) == Intent.STOP_SCENE
    assert match_intent("bas", in_rehearsal=True) == Intent.STOP_SCENE

    # "बस एक बंडल खोलो" and "यहीं रोककर सोचो..." are classroom teaching talk and MUST NOT match stop
    assert match_intent("बस एक बंडल खोलो", in_rehearsal=True) is None
    assert match_intent("बस 5 तीलियाँ निकालो", in_rehearsal=True) is None
    assert match_intent("यहीं रोककर सोचो, कितनी तीलियाँ बचीं?", in_rehearsal=True) is None

    # Outside rehearsal: stop keywords do NOT match stop_scene
    assert match_intent("बस", in_rehearsal=False) is None
    assert match_intent("रुको", in_rehearsal=False) is None


def test_intent_greeting_boundary_and_not_nahi() -> None:
    """'nahi' is NOT a greeting; 'hi' is a greeting only on word boundaries."""
    # "nahi" contains the substring "hi", but must NEVER match GREETING
    assert match_intent("nahi") != Intent.GREETING
    assert match_intent("nahi") == Intent.CONFIRM_NO

    # Proper greetings
    assert match_intent("नमस्ते") == Intent.GREETING
    assert match_intent("hello") == Intent.GREETING
    assert match_intent("hi") == Intent.GREETING
    assert match_intent("hey") == Intent.GREETING


def test_intent_global_keywords() -> None:
    """Tests global intents per spec/08 §8.3 table."""
    # help
    assert match_intent("मदद") == Intent.HELP
    assert match_intent("help") == Intent.HELP
    assert match_intent("menu") == Intent.HELP

    # next
    assert match_intent("आगे") == Intent.NEXT
    assert match_intent("अगला") == Intent.NEXT
    assert match_intent("शुरू") == Intent.NEXT
    assert match_intent("next") == Intent.NEXT

    # skip
    assert match_intent("छोड़ें") == Intent.SKIP
    assert match_intent("skip") == Intent.SKIP
    assert match_intent("chhodo") == Intent.SKIP

    # repeat
    assert match_intent("फिर से") == Intent.REPEAT
    assert match_intent("दोबारा") == Intent.REPEAT
    assert match_intent("repeat") == Intent.REPEAT

    # ask
    assert match_intent("सवाल: 43 में से 27 कैसे घटाएं?") == Intent.ASK
    assert match_intent("प्रश्न: हासिल क्या होता है?") == Intent.ASK
    assert match_intent("sawal") == Intent.ASK

    # lite_toggle
    assert match_intent("लाइट मोड") == Intent.LITE_TOGGLE
    assert match_intent("lite") == Intent.LITE_TOGGLE

    # progress
    assert match_intent("प्रगति") == Intent.PROGRESS
    assert match_intent("progress") == Intent.PROGRESS

    # consent
    assert match_intent("सहमति") == Intent.CONSENT
    assert match_intent("consent") == Intent.CONSENT

    # delete
    assert match_intent("मेरा डेटा हटाएँ") == Intent.DELETE
    assert match_intent("मेरा डाटा हटाएं") == Intent.DELETE
    assert match_intent("delete my data") == Intent.DELETE


def test_intent_button_ids() -> None:
    """Tests direct button id routing."""
    assert match_intent(button_id="confirm_yes") == Intent.CONFIRM_YES
    assert match_intent(button_id="confirm_no") == Intent.CONFIRM_NO
    assert match_intent(button_id="btn_yes") == Intent.CONFIRM_YES
    assert match_intent(button_id="btn_no") == Intent.CONFIRM_NO
    assert match_intent(button_id="btn_retry_speak") == Intent.CONFIRM_NO
    assert match_intent(button_id="btn_skip") == Intent.SKIP
    assert match_intent(button_id="btn_continue") == Intent.NEXT
    assert match_intent(button_id="btn_replay") == Intent.REPEAT


def test_extract_ask_query() -> None:
    """Tests extraction of user question after ASK keyword prefix."""
    q = extract_ask_query("सवाल: 43 में से 27 कैसे घटाएँ?")
    assert q == "43 में से 27 कैसे घटाएँ?"

    q2 = extract_ask_query("प्रश्न बंडल कैसे खोलते हैं?")
    assert q2 == "बंडल कैसे खोलते हैं?"


def test_normalize_intent_text() -> None:
    """Ensures NFC normalization and space collapsing."""
    raw = "  नमस्ते \t  "
    assert normalize_intent_text(raw) == "नमस्ते"
