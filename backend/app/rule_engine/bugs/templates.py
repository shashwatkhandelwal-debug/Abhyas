"""Step templates and rendering matching spec/04 §4.2."""

from typing import Any

from backend.app.rule_engine.domain import Step

STEP_TEMPLATES: dict[str, str] = {
    # Subtraction
    "SUB_CANNOT": "{u_top} में से {u_bot} नहीं घटता",
    "SUB_SWAP": "तो {u_bot} में से {u_top} घटाया, {d_u} आया",
    "SUB_TENS": "{t_top} में से {t_bot} घटाया, {d_t} आया",
    "REGROUP_OPEN_BUNDLE": "एक बंडल खोला, {u_new} तीलियाँ हो गईं, {t_left} बंडल बचे",
    "BORROW_NO_DEC": "{u_top} के आगे 1 लगाया, {u_new} में से {u_bot} घटाया, {d_u} आया",
    "WRITE_ZERO": "नहीं घटा तो 0 लिख दिया",
    "SUB_UNITS_NORMAL": "{u_top} में से {u_bot} घटाया, {d_u} आया",
    # Addition
    "ADD_UNITS": "{ua} और {ub} जोड़े, {s} आया",
    "ADD_WRITE_ALL": "{s} पूरा नीचे लिख दिया",
    "ADD_DROP_CARRY": "{s} में से {s_u} लिखा",
    "ADD_CARRY": "{s_u} लिखा, 1 हासिल ऊपर रखा",
    "ADD_WRONG_CARRY": "{s_t} लिखा, {s_u} हासिल ऊपर रखा",
    "ADD_TENS": "{ta} और {tb}{carry_txt} जोड़े, {t} आया",
    # Place value
    "PV_COUNT_BUNDLES": "{tens} बंडल और {ones} तीलियाँ, सब गिनीं",
    "PV_BUNDLE_TEN": "एक बंडल में 10 तीलियाँ, तो {tens} बंडल में {tens10}",
    "PV_CONCAT": "{tens10} और {ones}, तो {answer} लिखा",
    "PV_REVERSE": "पहले {ones} लिखा फिर {tens}",
    # Literacy
    "READ_AKSHARS": "{aksharas}",
    "READ_NO_MATRA": "{bare}",
    "LETTER_NAME": "{cons} से {kw}",
    "READ_GUESS": "{first} से {guess}",
    # Comparing two-digit numbers
    "CMP_ONES_FIRST": "{u_a} और {u_b} में {u_big} बड़ा है, तो {big} बड़ा",
    "CMP_TENS_FIRST": "{t_a} बंडल और {t_b} बंडल, {t_big} बंडल ज़्यादा, तो {big} बड़ा",
    "CMP_TENS_SAME": "दोनों में {t} बंडल हैं",
    "CMP_ONES_AFTER": "तीलियाँ {u_a} और {u_b}, {u_big} ज़्यादा, तो {big} बड़ा",
    "CMP_EQUAL": "दोनों {a} हैं, बराबर",
    # Common
    "ANSWER": "{answer}",
}


def make_step(
    code: str,
    nums: list[int] | None = None,
    words: list[str] | None = None,
    **kwargs: Any,
) -> Step:
    """Renders a Step template with formatted Hindi text and associated tokens."""
    template = STEP_TEMPLATES.get(code, "{answer}")
    text_hi = template.format(**kwargs)
    return Step(
        code=code,
        nums=nums or [],
        words=words or [],
        text_hi=text_hi,
    )
