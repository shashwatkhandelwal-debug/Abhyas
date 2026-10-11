"""Literacy procedural bug rules matching spec/04 §4.2."""

import re
from typing import Any

from backend.app.rule_engine.bugs.akshar import join_akshars, split_akshars, strip_matras
from backend.app.rule_engine.bugs.registry import NotApplicable, register_bug
from backend.app.rule_engine.bugs.templates import make_step
from backend.app.rule_engine.domain import BugOutput, Problem

DEFAULT_GUESS_LEXICON: dict[str, list[str]] = {
    "म": ["मछली", "मगर"],
    "प": ["पतंग", "पत्ता"],
    "क": ["कमल", "कलम"],
    "ग": ["गमला", "गाय"],
    "ब": ["बकरी", "बत्तख"],
    "न": ["नल", "नदी"],
    "र": ["रथ", "रात"],
    "स": ["सेब", "सूरज"],
}


def _unpack_word(problem: Problem) -> str:
    """Validates and unpacks a literacy reading problem."""
    if problem.type != "read_word":
        raise NotApplicable(f"Reading rule not applicable to problem type '{problem.type}'")
    if not problem.word:
        raise NotApplicable("Reading problem requires 'word'")
    return problem.word.strip()


def read_correct(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Correct reading: reads the full word and blends aksharas (§4.2).

    Examples:
    मेला -> मेला
    पानी -> पानी
    किताब -> किताब
    गुड़िया -> गुड़िया
    """
    word = _unpack_word(problem)
    aksharas = split_akshars(word)

    steps = [
        make_step(
            "READ_AKSHARS",
            words=aksharas,
            aksharas=join_akshars(aksharas, sep=" - "),
        ),
        make_step("ANSWER", words=[word], answer=word),
    ]
    return BugOutput(rule_id="CORRECT_READ", answer=word, steps=steps)


def matra_drop(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: drops all dependent vowel signs and ं ँ ः (§4.2).

    Examples:
    मेला -> मल
    पानी -> पन
    किताब -> कतब
    गुड़िया -> गड़य
    """
    word = _unpack_word(problem)
    bare = strip_matras(word)

    steps = [
        make_step("READ_NO_MATRA", words=[bare], bare=bare),
        make_step("ANSWER", words=[bare], answer=bare),
    ]
    return BugOutput(rule_id="MATRA_DROP", answer=bare, steps=steps)


def first_akshar_guess(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: reads first akshar, guesses a familiar word starting with same consonant (§4.2).

    Uses guess_lexicon from context/scenario if present. If guess equals the target word,
    uses the second entry.

    Examples:
    मेला -> मछली
    पानी -> पतंग
    किताब -> कमल
    गुड़िया -> गमला
    """
    word = _unpack_word(problem)
    aksharas = split_akshars(word)
    first_akshar = aksharas[0] if aksharas else word

    # Extract base consonant from first akshar
    consonant_match = re.search(r"[\u0915-\u0939]", first_akshar)
    base_consonant = consonant_match.group(0) if consonant_match else first_akshar

    lexicon = DEFAULT_GUESS_LEXICON
    if context and "guess_lexicon" in context and isinstance(context["guess_lexicon"], dict):
        lexicon = context["guess_lexicon"]

    candidates = lexicon.get(base_consonant, [f"{first_akshar}ल", f"{first_akshar}म"])
    guess = candidates[0]
    if guess == word and len(candidates) > 1:
        guess = candidates[1]

    steps = [
        make_step(
            "READ_GUESS",
            words=[first_akshar, guess],
            first=first_akshar,
            guess=guess,
        ),
        make_step("ANSWER", words=[guess], answer=guess),
    ]
    return BugOutput(rule_id="FIRST_AKSHAR_GUESS", answer=guess, steps=steps)


def akshar_by_akshar(problem: Problem, context: dict[str, Any] | None = None) -> BugOutput:
    """Misconception: sounds each akshar separately, cannot blend (§4.2).

    Answer = aksharas joined by ' - '.

    Examples:
    मेला -> मे - ला
    पानी -> पा - नी
    किताब -> कि - ता - ब
    गुड़िया -> गु - ड़ि - या
    """
    word = _unpack_word(problem)
    aksharas = split_akshars(word)
    joined = join_akshars(aksharas, sep=" - ")

    steps = [
        make_step("READ_AKSHARS", words=aksharas, aksharas=joined),
        make_step("ANSWER", words=[joined], answer=joined),
    ]
    return BugOutput(rule_id="AKSHAR_BY_AKSHAR", answer=joined, steps=steps)


# Register literacy bugs
register_bug(
    rule_id="MATRA_DROP",
    fn=matra_drop,
    correct_fn=read_correct,
    kind="literacy",
    problem_types=["read_word"],
    description_hi="मात्राएँ छोड़कर केवल मूल अक्षर पढ़ना",
    research_ref="NIPUN Bharat / Pratham reading level guidance",
)

register_bug(
    rule_id="FIRST_AKSHAR_GUESS",
    fn=first_akshar_guess,
    correct_fn=read_correct,
    kind="literacy",
    problem_types=["read_word"],
    description_hi="पहला अक्षर देखकर परिचित शब्द का अनुमान लगाना",
    research_ref="NIPUN Bharat / Pratham FLN research",
)

register_bug(
    rule_id="AKSHAR_BY_AKSHAR",
    fn=akshar_by_akshar,
    correct_fn=read_correct,
    kind="literacy",
    problem_types=["read_word"],
    description_hi="अक्षरों को अलग-अलग बोलना पर मिलाकर न पढ़ पाना (ब्लेंडिंग की कमी)",
    research_ref="NIPUN Bharat FLN reading benchmarks",
)
