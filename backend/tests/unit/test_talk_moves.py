"""Talk-move line in the end-of-scene coach feedback (flag TALK_MOVES_ENABLED).

Fixed transcripts for each case, one-on-one and group, Hindi and English, address form she and he,
flag off and on, and through the real SessionService with a scripted act tagger. The line is built
from tagged acts only (no model), makes no wait-time claim, and keeps the quote badge working.
"""

# ruff: noqa: F811  (the scene harness fixture is reused by name)
from __future__ import annotations

import re
from collections.abc import Callable, Iterator

import pytest
from test_one_on_one_flow import A, Harness, harness, texts  # noqa: F401

from backend.app.config import settings
from backend.app.core.messages import (
    FEMININE_MARKERS,
    get_message,
    reset_ui_lang,
    set_ui_lang,
)
from backend.app.rehearsal.scene_store import TurnRecord
from backend.app.rule_engine.domain import TeachingAct
from backend.app.sessions import talk_moves as tm

EXPLAIN = TeachingAct.ASK_TO_EXPLAIN.value
TOLD = TeachingAct.TELL_ANSWER.value
REPEAT = TeachingAct.REPEAT_QUESTION.value
NEWQ = TeachingAct.GIVE_NEW_PROBLEM.value
CONCRETE = TeachingAct.CONCRETE_REPRESENTATION.value


def turn(text: str, acts: list[str], to: str | None = None, i: int = 0) -> TurnRecord:
    return TurnRecord(turn_index=i, transcript=text, acts=acts, addressed_child=to)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


@pytest.fixture(autouse=True)
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TALK_MOVES_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)


def lines(text: str) -> list[str]:
    return text.split("\n")


# ── one-on-one ──────────────────────────────────────────────────────────────────────────────
ASKED = "तुमने यह कैसे किया? एक-एक कदम बताओ।"


def test_one_on_one_asked_to_explain_has_strength_with_her_words(lang: str) -> None:
    out = tm.talk_move_line(
        [turn(ASKED, [EXPLAIN]), turn("बंडल गिनकर दिखाओ।", [CONCRETE], i=1)], one_on_one=True
    )
    head, strength, nxt = lines(out)[0], lines(out)[1], "\n".join(lines(out)[2:])
    assert head == get_message("tm_head")
    assert get_message("tm_strength_explain") in strength
    assert "«" in out and ASKED.split()[0] in out  # her own first words, in the quote form
    assert get_message("tm_next_keep") in nxt
    assert get_message("coach_quote_suffix", quote=ASKED.split("।")[0]).split("«")[0].strip() != ""


def test_one_on_one_quote_is_a_cut_prefix_of_her_own_line(lang: str) -> None:
    long = " ".join(f"शब्द{i}" for i in range(30)) + " कैसे किया?"
    out = tm.talk_move_line([turn(long, [EXPLAIN])], one_on_one=True)
    quote = re.search(r"«([^»]+)»", out)
    assert quote is not None
    words = quote.group(1).split()
    assert len(words) == settings.COACH_QUOTE_MAX_WORDS
    assert long.startswith(quote.group(1))


def test_quote_marks_in_her_line_never_break_the_badge(lang: str) -> None:
    out = tm.talk_move_line([turn("तुमने «यह» कैसे किया?", [EXPLAIN])], one_on_one=True)
    assert len(re.findall(r"«[^»]+»", out)) == 1
    assert out.count("«") == 1 and out.count("»") == 1


def test_one_on_one_told_the_answer_gets_a_next_step_and_no_strength(lang: str) -> None:
    out = tm.talk_move_line(
        [turn("35 आता है, लिखो।", [TOLD]), turn("अब ये करो।", [NEWQ], i=1)], one_on_one=True
    )
    assert lines(out) == [get_message("tm_head"), f"➡️ {get_message('tm_next_told')}"]
    assert "«" not in out


def test_one_on_one_only_checking_answers_asks_for_how_or_why(lang: str) -> None:
    out = tm.talk_move_line(
        [turn("फिर से बोलो।", [REPEAT]), turn("अब ये करो।", [NEWQ], i=1)], one_on_one=True
    )
    assert lines(out)[-1] == f"➡️ {get_message('tm_next_check')}"
    assert len(lines(out)) == 2  # heading and next step; no strength to name


def test_one_on_one_told_and_explained_names_both(lang: str) -> None:
    out = tm.talk_move_line(
        [turn(ASKED, [EXPLAIN]), turn("35 आता है।", [TOLD], i=1)], one_on_one=True
    )
    assert get_message("tm_strength_explain") in out
    assert lines(out)[-1] == f"➡️ {get_message('tm_next_told')}"


def test_one_on_one_no_move_at_all_still_gives_one_next_step(lang: str) -> None:
    out = tm.talk_move_line(
        [turn("शाबाश बेटा।", [TeachingAct.PRAISE_GENERIC.value])], one_on_one=True
    )
    assert lines(out) == [get_message("tm_head"), f"➡️ {get_message('tm_next_explain')}"]


# ── group ───────────────────────────────────────────────────────────────────────────────────
def test_group_named_child_explain_has_strength_but_no_quote(lang: str) -> None:
    out = tm.talk_move_line(
        [turn("रवि, तुमने कैसे किया?", [EXPLAIN], "ravi"), turn("सब बोलो।", [REPEAT], "all", 1)],
        one_on_one=False,
    )
    assert get_message("tm_strength_explain") in out
    assert "«" not in out  # a group scene carries no quote, as in the coach feedback


def test_group_named_child_without_explain_names_the_named_strength(lang: str) -> None:
    out = tm.talk_move_line(
        [turn("प्रिया, तुम बताओ।", [CONCRETE], "priya"), turn("अमन, तुम?", [CONCRETE], "aman", 1)],
        one_on_one=False,
    )
    assert get_message("tm_strength_named") in out
    assert lines(out)[-1] == f"➡️ {get_message('tm_next_explain')}"


def test_group_whole_class_only_suggests_calling_a_named_child(lang: str) -> None:
    out = tm.talk_move_line(
        [turn("बच्चों, कितने बचे?", [CONCRETE], "all"), turn("सब देखो।", [CONCRETE], "all", 1)],
        one_on_one=False,
    )
    assert get_message("tm_strength_class") in out
    assert lines(out)[-1] == f"➡️ {get_message('tm_next_named')}"


def test_group_counts_named_versus_whole_class() -> None:
    c = tm.count_turns(
        [
            turn("रवि, कैसे?", [EXPLAIN], "ravi"),
            turn("सब बोलो।", [REPEAT], "all", 1),
            turn("प्रिया, तुम?", [REPEAT], "priya", 2),
            turn("बताओ।", [CONCRETE], None, 3),
        ],
        one_on_one=False,
    )
    assert (c.turns, c.named, c.whole_class, c.explain, c.check_only, c.told) == (4, 2, 1, 1, 2, 0)


def test_one_on_one_ignores_the_named_versus_class_axis() -> None:
    c = tm.count_turns([turn("रवि, कैसे?", [EXPLAIN], "ravi")], one_on_one=True)
    assert c.named == 0 and c.whole_class == 0 and c.explain == 1


# ── what is skipped, and the honest limits ──────────────────────────────────────────────────
def test_no_teacher_turn_no_line() -> None:
    assert tm.talk_move_line([], one_on_one=True) == ""
    assert tm.talk_move_line([turn("", [EXPLAIN])], one_on_one=True) == ""


def test_stop_commands_and_how_to_questions_are_not_counted() -> None:
    c = tm.count_turns(
        [
            turn("बस", ["stop"]),
            turn("मैं बच्चे से कैसे पूछूँ?", [EXPLAIN]),
            turn(ASKED, [EXPLAIN], i=2),
        ],
        one_on_one=True,
    )
    assert c.turns == 1 and c.explain == 1


def test_no_wait_time_claim_anywhere_in_the_texts() -> None:
    for code in ("hi", "en"):
        for key in (
            "tm_head",
            "tm_strength_explain",
            "tm_strength_named",
            "tm_strength_class",
            "tm_next_told",
            "tm_next_check",
            "tm_next_named",
            "tm_next_explain",
            "tm_next_keep",
        ):
            text = get_message(key, lang=code).lower()
            assert "wait" not in text and "प्रतीक्षा" not in text and "सेकंड" not in text, key
            assert "research" not in text and "अध्ययन" not in text, key


@pytest.mark.parametrize("form", ["f", "m"])
def test_texts_exist_in_both_languages_and_have_no_feminine_only_wording(form: str) -> None:
    keys = [
        "tm_head",
        "tm_strength_explain",
        "tm_strength_named",
        "tm_strength_class",
        "tm_next_told",
        "tm_next_check",
        "tm_next_named",
        "tm_next_explain",
        "tm_next_keep",
    ]
    for key in keys:
        hi = get_message(key, form, lang="hi")
        en = get_message(key, form, lang="en")
        assert hi != en and hi.strip() and en.strip()
        assert not any(re.search(m, hi) for m in FEMININE_MARKERS), key
        assert not re.search(r"[ऀ-ॿ]", en), key


def test_output_is_deterministic() -> None:
    t = [turn(ASKED, [EXPLAIN]), turn("35 आता है।", [TOLD], i=1)]
    assert tm.talk_move_line(t, one_on_one=True) == tm.talk_move_line(list(t), one_on_one=True)


def test_flag_defaults_off_and_demo_mode_turns_it_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.config import v2_enabled

    assert settings.model_fields["TALK_MOVES_ENABLED"].default is False
    monkeypatch.setattr(settings, "TALK_MOVES_ENABLED", False)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert not v2_enabled(settings.TALK_MOVES_ENABLED)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert v2_enabled(settings.TALK_MOVES_ENABLED)


# ── through the real SessionService ─────────────────────────────────────────────────────────
def _coach_message(out: list) -> object:  # type: ignore[type-arg]
    """The coach advice bubble (the one with the strength and the next-step lines)."""
    return next(m for m in out if m.speaker == "coach" and "👍" in (m.text_hi or ""))


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["f", "m"])
async def test_one_on_one_feedback_carries_the_line_in_the_coach_bubble(
    lang: str, form: str, harness: Callable[[], Harness]
) -> None:
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया, छोटी में से बड़ी")
    ctx = await h.ctx()
    ctx.address_form = form
    h.script += [([A.ASK_TO_EXPLAIN], None, None)] * 2 + [([], None, None)]
    for _ in range(2):
        await h.say(ASKED)
    out = await h.say("बस")
    coach = _coach_message(out)
    assert coach.speaker == "coach"  # type: ignore[attr-defined]
    body = coach.text_hi  # type: ignore[attr-defined]
    assert get_message("tm_head", form) in body
    assert get_message("tm_strength_explain", form) in body
    # two quotes now (coach strength and talk-move strength), each one the existing badge form
    assert len(re.findall(r"«[^»]+»", body)) == 2
    assert body.index(get_message("tm_head", form)) > body.index("🔁")  # after the coach advice


@pytest.mark.asyncio
async def test_group_feedback_carries_the_line_without_a_quote(
    lang: str, harness: Callable[[], Harness]
) -> None:
    h = harness()
    await h.start("NUM_SUB_REGROUP_BUNDLES")
    await h.say(button="btn_listen")
    await h.say(button="btn_rehearse_group")
    h.script += [
        ([A.ASK_TO_EXPLAIN], "ravi", None),
        ([A.CONCRETE_REPRESENTATION], "all", None),
        ([A.ASK_TO_EXPLAIN], "priya", None),
        ([], None, None),
    ]
    await h.say("रवि, तुमने कैसे किया?")
    await h.say("सब देखो ये बंडल हैं।")
    await h.say("प्रिया, तुम बताओ कैसे?")
    out = await h.say("बस")
    body = _coach_message(out).text_hi  # type: ignore[attr-defined]
    assert get_message("tm_head") in body
    assert get_message("tm_strength_explain") in body
    assert "«" not in body.split(get_message("tm_head"))[1]


@pytest.mark.asyncio
async def test_flag_off_the_feedback_is_unchanged(
    lang: str, harness: Callable[[], Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TALK_MOVES_ENABLED", False)
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया, छोटी में से बड़ी")
    h.script += [([A.ASK_TO_EXPLAIN], None, None)] * 2 + [([], None, None)]
    for _ in range(2):
        await h.say(ASKED)
    out = await h.say("बस")
    assert get_message("tm_head") not in texts(out)


@pytest.mark.asyncio
async def test_told_answer_relapse_scene_names_telling_as_the_next_step(
    lang: str, harness: Callable[[], Harness]
) -> None:
    h = harness()
    await h.setup("NUM_SUB_REGROUP_BUNDLES", "ravi", "उल्टा घटा दिया, छोटी में से बड़ी")
    h.script += [([A.TELL_ANSWER], None, None), ([A.TELL_ANSWER], None, None), ([], None, None)]
    await h.say("उत्तर 35 है, लिखो।")
    await h.say("35 ही आता है।")
    out = await h.say("बस")
    body = _coach_message(out).text_hi  # type: ignore[attr-defined]
    assert get_message("tm_next_told") in body
    assert get_message("tm_strength_explain") not in body
