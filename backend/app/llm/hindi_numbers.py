"""Devanagari digits and Hindi number words ↔ int matching spec/05 §5.10 and spec/14 T05.

Provides:
- extract_numbers(text: str) -> list[int]
- to_words(n: int) -> str (0 to 199)
"""

import re
import unicodedata

# Canonical Hindi words for numbers 0 to 100
HINDI_NUMBER_WORDS_0_TO_100: dict[int, str] = {
    0: "शून्य",
    1: "एक",
    2: "दो",
    3: "तीन",
    4: "चार",
    5: "पाँच",
    6: "छह",
    7: "सात",
    8: "आठ",
    9: "नौ",
    10: "दस",
    11: "ग्यारह",
    12: "बारह",
    13: "तेरह",
    14: "चौदह",
    15: "पंद्रह",
    16: "सोलह",
    17: "सत्रह",
    18: "अठारह",
    19: "उन्नीस",
    20: "बीस",
    21: "इक्कीस",
    22: "बाईस",
    23: "तेईस",
    24: "चौबीस",
    25: "पच्चीस",
    26: "छब्बीस",
    27: "सत्ताईस",
    28: "अट्ठाईस",
    29: "उनतीस",
    30: "तीस",
    31: "इकत्तीस",
    32: "बत्तीस",
    33: "तैंतीस",
    34: "चौंतीस",
    35: "पैंतीस",
    36: "छत्तीस",
    37: "सैंतीस",
    38: "अड़तीस",
    39: "उनतालीस",
    40: "चालीस",
    41: "इकतालीस",
    42: "बयालीस",
    43: "तैंतालीस",
    44: "चवालीस",
    45: "पैंतालीस",
    46: "छियालीस",
    47: "सैंतालीस",
    48: "अड़तालीस",
    49: "उनचास",
    50: "पचास",
    51: "इक्यावन",
    52: "बावन",
    53: "तिरेपन",
    54: "चौवन",
    55: "पचपन",
    56: "छप्पन",
    57: "सत्तावन",
    58: "अट्ठावन",
    59: "उनसठ",
    60: "साठ",
    61: "इकसठ",
    62: "बासठ",
    63: "तिरसठ",
    64: "चौंसठ",
    65: "पैंसठ",
    66: "छियासठ",
    67: "सरसठ",
    68: "अड़सठ",
    69: "उनहत्तर",
    70: "सत्तर",
    71: "इकहत्तर",
    72: "बहत्तर",
    73: "तिहत्तर",
    74: "चौहत्तर",
    75: "पचहत्तर",
    76: "छिहत्तर",
    77: "सतहत्तर",
    78: "अठहत्तर",
    79: "उनासी",
    80: "अस्सी",
    81: "इक्यासी",
    82: "बयासी",
    83: "तिरासी",
    84: "चौरासी",
    85: "पचासी",
    86: "छियासी",
    87: "सत्तासी",
    88: "अट्ठासी",
    89: "नवासी",
    90: "नब्बे",
    91: "इक्यानवे",
    92: "बानवे",
    93: "तिरानवे",
    94: "चौरानवे",
    95: "पंचानवे",
    96: "छियानवे",
    97: "सत्तानवे",
    98: "अट्ठानवे",
    99: "निन्यानवे",
    100: "सौ",
}

# Devanagari numerals
DEVANAGARI_DIGITS = "०१२३४५६७८९"

# Spelling and Roman Hinglish variants mapped to integer values
VARIANTS_MAP: dict[str, int] = {
    # 0
    "शून्य": 0,
    "zero": 0,
    "shunya": 0,
    "shunye": 0,
    # 1-10
    "एक": 1,
    "ek": 1,
    "one": 1,
    "दो": 2,
    "do": 2,
    "two": 2,
    "तीन": 3,
    "teen": 3,
    "tin": 3,
    "three": 3,
    "चार": 4,
    "char": 4,
    "chaar": 4,
    "four": 4,
    "पाँच": 5,
    "पांच": 5,
    "paanch": 5,
    "panch": 5,
    "five": 5,
    "छह": 6,
    "छः": 6,
    "छ": 6,
    "chhah": 6,
    "chhe": 6,
    "che": 6,
    "six": 6,
    "सात": 7,
    "saat": 7,
    "sat": 7,
    "seven": 7,
    "आठ": 8,
    "aath": 8,
    "ath": 8,
    "eight": 8,
    "नौ": 9,
    "nau": 9,
    "nine": 9,
    "दस": 10,
    "das": 10,
    "ten": 10,
    # 11-20
    "ग्यारह": 11,
    "gyarah": 11,
    "gyaarah": 11,
    "बारह": 12,
    "barah": 12,
    "baarah": 12,
    "तेरह": 13,
    "terah": 13,
    "tehrah": 13,
    "चौदह": 14,
    "chaudah": 14,
    "chodah": 14,
    "पंद्रह": 15,
    "पन्द्रह": 15,
    "pandrah": 15,
    "pandrahh": 15,
    "सोलह": 16,
    "solah": 16,
    "सत्रह": 17,
    "satrah": 17,
    "अठारह": 18,
    "atharah": 18,
    "athaarah": 18,
    "उन्नीस": 19,
    "unnees": 19,
    "unnis": 19,
    "बीस": 20,
    "bees": 20,
    "bis": 20,
    # 21-30
    "इक्कीस": 21,
    "ikkees": 21,
    "ikkis": 21,
    "बाईस": 22,
    "baees": 22,
    "bais": 22,
    "तेईस": 23,
    "teees": 23,
    "teis": 23,
    "चौबीस": 24,
    "chaubees": 24,
    "chaubis": 24,
    "पच्चीस": 25,
    "पचीस": 25,
    "pachhees": 25,
    "pachis": 25,
    "pachchees": 25,
    "छब्बीस": 26,
    "chhabbees": 26,
    "chhabbis": 26,
    "सत्ताईस": 27,
    "sattaees": 27,
    "sattais": 27,
    "अट्ठाईस": 28,
    "atthaees": 28,
    "atthais": 28,
    "उनतीस": 29,
    "उनत्तीस": 29,
    "untees": 29,
    "untis": 29,
    "तीस": 30,
    "tees": 30,
    "tis": 30,
    # 31-40
    "इकत्तीस": 31,
    "iktees": 31,
    "iktis": 31,
    "बत्तीस": 32,
    "battees": 32,
    "battis": 32,
    "तैंतीस": 33,
    "तेतीस": 33,
    "taintees": 33,
    "tentis": 33,
    "चौंतीस": 34,
    "चौतीस": 34,
    "chauntees": 34,
    "chautis": 34,
    "पैंतीस": 35,
    "पैतीस": 35,
    "paintees": 35,
    "paintis": 35,
    "छत्तीस": 36,
    "chhattees": 36,
    "chhattis": 36,
    "सैंतीस": 37,
    "सैतीस": 37,
    "saintees": 37,
    "saintis": 37,
    "अड़तीस": 38,
    "adtees": 38,
    "adtis": 38,
    "artees": 38,
    "उनतालीस": 39,
    "उनचालीस": 39,
    "untalees": 39,
    "untalis": 39,
    "unchalis": 39,
    "चालीस": 40,
    "chalees": 40,
    "chaalees": 40,
    "chalis": 40,
    # 41-50
    "इकतालीस": 41,
    "इकचालीस": 41,
    "iktalees": 41,
    "iktalis": 41,
    "बयालीस": 42,
    "bayalees": 42,
    "bayalis": 42,
    "तैंतालीस": 43,
    "तैतालीस": 43,
    "taintalees": 43,
    "taintalis": 43,
    "चवालीस": 44,
    "चौवालीस": 44,
    "chawalees": 44,
    "chawalis": 44,
    "chauwalees": 44,
    "पैंतालीस": 45,
    "पैतालीस": 45,
    "paintalees": 45,
    "paintalis": 45,
    "छियालीस": 46,
    "chhiyalees": 46,
    "chhiyalis": 46,
    "सैंतालीस": 47,
    "सैतालीस": 47,
    "saintalees": 47,
    "saintalis": 47,
    "अड़तालीस": 48,
    "adtalees": 48,
    "adtalis": 48,
    "artalees": 48,
    "उनचास": 49,
    "उंचास": 49,
    "unchaas": 49,
    "unchas": 49,
    "पचास": 50,
    "pachaas": 50,
    "pachas": 50,
    # 51-60
    "इक्यावन": 51,
    "इक्याबन": 51,
    "इकावन": 51,
    "ikyaavan": 51,
    "ikyawan": 51,
    "बावन": 52,
    "बाबन": 52,
    "baawan": 52,
    "bawan": 52,
    "तिरेपन": 53,
    "तिर्पण": 53,
    "तरेपन": 53,
    "tirepan": 53,
    "चौवन": 54,
    "चौबन": 54,
    "chauwan": 54,
    "chauban": 54,
    "पचपन": 55,
    "pachpan": 55,
    "छप्पन": 56,
    "chhappan": 56,
    "सत्तावन": 57,
    "sattawan": 57,
    "sattaavan": 57,
    "अट्ठावन": 58,
    "atthaawan": 58,
    "atthawan": 58,
    "उनसठ": 59,
    "unsath": 59,
    "साठ": 60,
    "saath": 60,
    "sath": 60,
    # 61-70
    "इकसठ": 61,
    "iksath": 61,
    "बासठ": 62,
    "baasath": 62,
    "basath": 62,
    "तिरसठ": 63,
    "तेरसठ": 63,
    "tirsath": 63,
    "चौंसठ": 64,
    "चौसठ": 64,
    "chaunsath": 64,
    "chausath": 64,
    "पैंसठ": 65,
    "पैसठ": 65,
    "painsath": 65,
    "paisath": 65,
    "छियासठ": 66,
    "chhiyasath": 66,
    "सरसठ": 67,
    "sarsath": 67,
    "अड़सठ": 68,
    "adsath": 68,
    "arsath": 68,
    "उनहत्तर": 69,
    "unhattar": 69,
    "सत्तर": 70,
    "sattar": 70,
    # 71-80
    "इकहत्तर": 71,
    "ikhattar": 71,
    "बहत्तर": 72,
    "bahattar": 72,
    "तिहत्तर": 73,
    "tihattar": 73,
    "चौहत्तर": 74,
    "chauhattar": 74,
    "पचहत्तर": 75,
    "pachhattar": 75,
    "छिहत्तर": 76,
    "chhihattar": 76,
    "सतहत्तर": 77,
    "sathattar": 77,
    "satattar": 77,
    "अठहत्तर": 78,
    "athhattar": 78,
    "athttar": 78,
    "उनासी": 79,
    "उन्यासी": 79,
    "unasi": 79,
    "unyasi": 79,
    "अस्सी": 80,
    "assi": 80,
    # 81-90
    "इक्यासी": 81,
    "इकासी": 81,
    "ikyaasi": 81,
    "ikyasi": 81,
    "बयासी": 82,
    "bayaasi": 82,
    "bayasi": 82,
    "तिरासी": 83,
    "tiraasi": 83,
    "tirasi": 83,
    "चौरासी": 84,
    "chauraasi": 84,
    "chaurasi": 84,
    "पचासी": 85,
    "pachaasi": 85,
    "pachasi": 85,
    "छियासी": 86,
    "chhiyaasi": 86,
    "chhiyasi": 86,
    "सत्तासी": 87,
    "sattaasi": 87,
    "sattasi": 87,
    "अट्ठासी": 88,
    "atthaasi": 88,
    "tthasi": 88,
    "नवासी": 89,
    "nawaasi": 89,
    "nawasi": 89,
    "नब्बे": 90,
    "nabbe": 90,
    "nabbey": 90,
    # 91-100
    "इक्यानवे": 91,
    "इक्यानबे": 91,
    "इकानवे": 91,
    "ikyanve": 91,
    "ikyanbe": 91,
    "बानवे": 92,
    "बानबे": 92,
    "baanve": 92,
    "banve": 92,
    "banbe": 92,
    "तिरानवे": 93,
    "तिरानबे": 93,
    "tiranve": 93,
    "tiranbe": 93,
    "चौरानवे": 94,
    "चौरानबे": 94,
    "chauranve": 94,
    "chauranbe": 94,
    "पंचानवे": 95,
    "पंचानबे": 95,
    "पचानवे": 95,
    "panchanve": 95,
    "panchanbe": 95,
    "छियानवे": 96,
    "छियानबे": 96,
    "chhiyanve": 96,
    "chhiyanbe": 96,
    "सत्तानवे": 97,
    "सत्तानबे": 97,
    "sattanve": 97,
    "sattanbe": 97,
    "अट्ठानवे": 98,
    "अट्ठानबे": 98,
    "atthanve": 98,
    "atthanbe": 98,
    "निन्यानवे": 99,
    "निन्यानबे": 99,
    "ninyanve": 99,
    "ninyanbe": 99,
    "सौ": 100,
    "sau": 100,
}

# Add canonical mappings
for _n, _w in HINDI_NUMBER_WORDS_0_TO_100.items():
    VARIANTS_MAP[_w] = _n


def to_words(n: int) -> str:
    """Converts an integer (0 to 199) to canonical Hindi words.

    Examples:
    0 -> 'शून्य'
    45 -> 'पैंतालीस'
    100 -> 'सौ'
    101 -> 'एक सौ एक'
    145 -> 'एक सौ पैंतालीस'
    """
    if not isinstance(n, int):
        raise TypeError(f"Expected int, got {type(n).__name__}")
    if n < 0 or n > 199:
        raise ValueError(f"Number out of supported range (0-199): {n}")

    if n <= 100:
        return HINDI_NUMBER_WORDS_0_TO_100[n]

    remainder = n - 100
    rem_word = HINDI_NUMBER_WORDS_0_TO_100[remainder]
    return f"एक सौ {rem_word}"


def extract_numbers(text: str) -> list[int]:
    """Extracts all numbers from text in appearance order.

    Handles:
    - Arabic digits (e.g. 52, 17, 713)
    - Devanagari numerals (e.g. ५२ -> 52, १७ -> 17)
    - Hindi number words 0-100 (e.g. बावन, सत्रह, पैंतालीस, सौ)
    - Compound hundreds (e.g. एक सौ पैंतालीस -> 145)
    - Roman Hinglish number words (e.g. paintalis -> 45, baawan -> 52)
    """
    if not text:
        return []

    norm_text = unicodedata.normalize("NFC", text).strip()
    spans: list[tuple[int, int, int, bool]] = []  # (start, end, val, is_ambiguous_two)

    # 1. First, check for compound hundreds like "एक सौ <number>" or "सौ <number>"
    hundred_patterns = [
        (r"(?<![\u0900-\u097F\w])(?:एक\s+)?सौ\s+([\u0900-\u097F]+)(?![\u0900-\u097F\w])", True),
        (r"\b(?:ek\s+)?sau\s+([a-zA-Z]+)\b", False),
    ]
    for pat, is_dev in hundred_patterns:
        for m in re.finditer(pat, norm_text, flags=re.IGNORECASE):
            sub_word = m.group(1).lower() if not is_dev else m.group(1)
            val = VARIANTS_MAP.get(sub_word)
            if val is not None and 1 <= val < 100:
                spans.append((m.start(), m.end(), 100 + val, False))

    # 2. Check for Arabic digits
    for m in re.finditer(r"\b\d+\b", norm_text):
        spans.append((m.start(), m.end(), int(m.group(0)), False))

    # 3. Check for Devanagari numerals
    for m in re.finditer(r"[" + DEVANAGARI_DIGITS + r"]+", norm_text):
        val_str = ""
        for ch in m.group(0):
            val_str += str(DEVANAGARI_DIGITS.index(ch))
        spans.append((m.start(), m.end(), int(val_str), False))

    # 4. Check for individual words (Hindi and Roman) sorted by length desc
    # Sort keys by length descending to match greedily
    sorted_words = sorted(VARIANTS_MAP.keys(), key=len, reverse=True)
    for word in sorted_words:
        is_latin = word.isascii()
        if is_latin:
            pattern = rf"\b{re.escape(word)}\b"
            flags = re.IGNORECASE
        else:
            pattern = rf"(?<![\u0900-\u097F\w]){re.escape(word)}(?![\u0900-\u097F\w])"
            flags = re.RegexFlag(0)

        for m in re.finditer(pattern, norm_text, flags=flags):
            val = VARIANTS_MAP[word]
            matched_raw = norm_text[m.start() : m.end()].lower()
            is_ambiguous = val == 2 and matched_raw in {"दो", "do"}
            spans.append((m.start(), m.end(), val, is_ambiguous))

    # Filter overlapping spans: keep earliest starting, and longer span on collision
    # Sort by start asc, length desc
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    chosen_spans: list[tuple[int, int, int, bool]] = []
    last_end = -1
    for start, end, val, is_ambiguous in spans:
        if start >= last_end:
            chosen_spans.append((start, end, val, is_ambiguous))
            last_end = end

    # Counting nouns that disambiguate "दो" as number 2
    counting_nouns_pattern = re.compile(
        r"^(?:"
        r"बंडल|bundle|"
        r"तीली|तीलियाँ|तीलीयाँ|तीलियों|stick|"
        r"बच्च|child|kid|"
        r"लोग|people|"
        r"टॉफ़|टॉफ|toffee|"
        r"किताब|book|"
        r"आम|mango|"
        r"सेब|apple|"
        r"दहाई|tens|"
        r"इकाई|ones|"
        r"अंक|संख्या|digit|number|"
        r"कदम|step|"
        r"गेंद|ball|"
        r"पेंसिल|pencil|"
        r"पेन|pen|"
        r"रुप|rupee|rs|"
        r"पैसे|पैसा|paise|"
        r"डिब्ब|box|"
        r"सवाल|प्रश्न|question|"
        r"फूल|flower|"
        r"कंकड़|पत्थर|pebble|stone"
        r")",
        re.IGNORECASE,
    )
    connector_pattern = re.compile(
        r"^[\s।,!\?;:\"\'\(\)\-–—\./]*(?:और|तथा|या|प्लस|माइनस|\+|\-|and|plus|minus)?[\s।,!\?;:\"\'\(\)\-–—\./]*$",
        re.IGNORECASE,
    )

    results: list[int] = []
    for i, (start, end, val, is_ambiguous) in enumerate(chosen_spans):
        if is_ambiguous:
            next_to_num = False
            if i > 0:
                sep_prev = norm_text[chosen_spans[i - 1][1] : start]
                if connector_pattern.match(sep_prev):
                    next_to_num = True
            if not next_to_num and i < len(chosen_spans) - 1:
                sep_next = norm_text[end : chosen_spans[i + 1][0]]
                if connector_pattern.match(sep_next):
                    next_to_num = True

            after_text = norm_text[end:].lstrip(" \t\r\n।,!?;:\"'()-–—.")
            before_counting_noun = bool(counting_nouns_pattern.match(after_text))

            if not (next_to_num or before_counting_noun):
                continue

        results.append(val)

    return results
