"""Letter name instead of letter sound (Track B scene LIT_LETTER_SOUND_PAIRS).

The stored handbook chunks name no confusable letter pair, so the scene uses the other
confusion they do describe: a letter has a name and a sound, and the child gives the alphabet
chart's name ("ब से बतख") instead of sounding the letter out and reading the word.
"""

import re
from typing import Any

from backend.app.rule_engine.bugs.akshar import split_akshars
from backend.app.rule_engine.bugs.literacy import read_correct
from backend.app.rule_engine.bugs.registry import NotApplicable, register_bug
from backend.app.rule_engine.bugs.templates import make_step
from backend.app.rule_engine.domain import BugOutput, Problem

CHART_KEYWORDS: dict[str, list[str]] = {
    "क": ["कबूतर", "कलम"],
    "ग": ["गाय", "गमला"],
    "ब": ["बतख", "बस"],
    "न": ["नल", "नाव"],
    "म": ["मछली", "मटर"],
    "स": ["सेब", "सड़क"],
    "र": ["रथ", "रस्सी"],
    "ल": ["लट्टू", "लड्डू"],
}


def letter_name_for_sound(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """The child names the first letter from the chart instead of reading the word.

    Examples:
    बकरी -> ब से बतख
    कमल -> क से कबूतर
    गमला -> ग से गाय
    """
    if problem.type != "read_word" or not problem.word:
        raise NotApplicable("Letter-sound rule needs a 'read_word' problem with a word")
    word = problem.word.strip()
    aksharas = split_akshars(word)
    first = aksharas[0] if aksharas else word
    m = re.search(r"[क-ह]", first)
    cons = m.group(0) if m else first
    lexicon = CHART_KEYWORDS
    if context and isinstance(context.get("guess_lexicon"), dict) and context["guess_lexicon"]:
        lexicon = context["guess_lexicon"]
    candidates = lexicon.get(cons, [f"{cons}ल"])
    kw = candidates[0]
    if kw == word and len(candidates) > 1:
        kw = candidates[1]
    answer = f"{cons} से {kw}"
    steps = [
        make_step("LETTER_NAME", words=[cons, "से", kw], cons=cons, kw=kw),
        make_step("ANSWER", words=[answer], answer=answer),
    ]
    return BugOutput(rule_id="LETTER_NAME_FOR_SOUND", answer=answer, steps=steps)


register_bug(
    rule_id="LETTER_NAME_FOR_SOUND",
    fn=letter_name_for_sound,
    correct_fn=read_correct,
    kind="literacy",
    problem_types=["read_word"],
    description_hi="अक्षर की ध्वनि बोलने के बजाय चार्ट वाला नाम बोलना (ब से बतख)",
    research_ref="NIPUN Bharat: alphabet knowledge (letter names and letter sounds)",
)
