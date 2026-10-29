"""Content integrity of the class check-in: tips, citations, struggle ids and catalog keys.

The check-in shows only what is stored: the tip is the struggle's own paraphrase of its handbook
chunks, cited by those chunks. These tests keep that true as the content files change.
"""

from __future__ import annotations

import re

import pytest

from backend.app.class_profile import checkin_flow
from backend.app.class_profile.library import _chunk_index, citations, load_library
from backend.app.core.messages import DEFAULT_LANG, get_catalog

LIB = load_library()
MODULES = checkin_flow.modules(LIB)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN_PASSAGE = re.compile(
    r"(?:[A-Za-z]{2,}[ ,;:-]+){4,}[A-Za-z]{2,}"
)  # five or more English words


def _checkin_keys() -> set[str]:
    keys = {
        checkin_flow.BTN_START,
        checkin_flow.BTN_MORE,
        checkin_flow.BTN_PRACTICE,
        checkin_flow.BTN_HANDBOOK,
        checkin_flow.BTN_RESUME,
        *checkin_flow.OUTCOME_BUTTONS,
        "chk_module_ask",
        "chk_more_ask",
        "chk_outcome_ask",
        "chk_struggle_ask",
        "chk_pick_button",
        "chk_well_ack",
        "chk_well_next",
        "chk_tip",
        "chk_tip_missing",
        "chk_practice_yes",
        "chk_practice_none",
        "chk_already",
        "chk_command_words",
        "chk_in_scene_practice",
        "chk_scene_waiting",
    }
    keys |= {f"{checkin_flow.MODULE_PREFIX}{m.id}" for m in MODULES}
    keys |= {f"{checkin_flow.STRUGGLE_PREFIX}{s.id}" for s in LIB.struggles}
    return keys


def test_every_tip_chunk_resolves_to_a_stored_chunk() -> None:
    index = _chunk_index()
    for s in LIB.struggles:
        assert s.chunk_ids, s.id
        for chunk_id in s.chunk_ids:
            assert chunk_id in index, f"{s.id}: chunk {chunk_id} is not stored"
        found = citations(s.chunk_ids)
        assert len(found) == len(s.chunk_ids), s.id
        assert all(c.source_short_hi for c in found), s.id


def test_tip_shown_is_the_stored_paraphrase_with_its_chunk_citations() -> None:
    from backend.app.sessions.state_machine import SessionContext

    for s in LIB.struggles:
        ctx = SessionContext.model_construct(address_form="f", current_state=None)
        msgs = checkin_flow.result_messages(ctx, s)
        tip_msg = msgs[0]
        assert s.tip_hi in tip_msg.text_hi, s.id
        assert {c.chunk_id for c in tip_msg.citations} == set(s.chunk_ids), s.id


def test_tips_have_text_and_no_foreign_language_passage() -> None:
    for s in LIB.struggles + [LIB.other]:  # type: ignore[operator]
        assert s.tip_hi.strip() and s.tip_en.strip()
        assert DEVANAGARI.search(s.tip_hi), "Hindi tip has no Devanagari"
        assert not LATIN_PASSAGE.search(s.tip_hi), f"English passage in Hindi tip: {s.tip_hi}"
        assert not DEVANAGARI.search(s.tip_en), f"Hindi in English tip: {s.tip_en}"


def test_every_checkin_struggle_exists_in_the_library() -> None:
    ids = set(LIB.ids())
    for m in MODULES:
        assert m.struggle_ids, m.id
        assert set(m.struggle_ids) <= ids
    covered = {sid for m in MODULES for sid in m.struggle_ids}
    assert covered == ids


@pytest.mark.parametrize("lang", [DEFAULT_LANG, "en"])
def test_catalog_has_every_checkin_key(lang: str) -> None:
    catalog = get_catalog(lang=lang)
    missing = sorted(k for k in _checkin_keys() if not catalog.has(k))
    assert not missing, f"{lang} catalog is missing {missing}"
