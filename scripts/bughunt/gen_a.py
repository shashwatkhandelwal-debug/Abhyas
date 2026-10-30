# ruff: noqa
"""Generate journey A (onboarding) variants as JSON files."""

import json, pathlib

out = pathlib.Path(__file__).parent / "journeys"
LONG = (
    "रवि, तुम्हारा जवाब मैंने सुना, लेकिन मैं समझना चाहता हूँ कि तुमने यह कैसे किया। "
    "पहले तुमने ऊपर वाली संख्या देखी, फिर नीचे वाली। उसके बाद क्या किया, ज़रा धीरे-धीरे बताओ। "
    "इकाई में 2 में से 7 नहीं घटता, तो तुमने क्या किया? दहाई वाले अंक के साथ क्या हुआ? "
    "मुझे अपना तरीका बताओ ताकि हम सब साथ में देख सकें कि कहाँ गड़बड़ हुई और उसे ठीक कर सकें। "
    "बताओ, मैं ध्यान से सुन रहा हूँ, कोई जल्दी नहीं है, आराम से सोचकर बताओ रवि।"
)
assert len(LONG) >= 380, len(LONG)
TELL = "ऊपर 52 नीचे 17 लिखो, 12 में से 7 घटाओ, 4 में से 1 घटाओ, अब बताओ क्या आंसर है"
variants = {
    "A1_m_hi": dict(
        lang="hi",
        g="Teacher (he)",
        gh="शिक्षक",
        names=["हाँ", "जी", "हाँ, मेरा नाम सुनील है"],
        consent=["No_typed", "learn", "agree"],
        arp=["bad", "no"],
        r1="रवि, 45 कैसे आया?",
        r2=TELL,
    ),
    "A2_f_hi": dict(
        lang="hi",
        gh="शिक्षिका",
        names=["Riya"],
        consent=["agree"],
        arp=["bad", "DEMO"],
        r1=TELL,
        r2="रवि, 45 कैसे आया?",
    ),
    "A3_m_en": dict(
        lang="en",
        gh="Teacher (he)",
        names=["My name is Arjun"],
        consent=["agree"],
        arp=["DEMO"],
        r1="what is the weather today? tell me a joke",
        r2="Ravi, how did you get 45?",
    ),
    "A4_f_en": dict(
        lang="en",
        gh="Teacher (she)",
        names=["मेरा नाम रिया है।"],
        consent=["learn", "agree"],
        arp=["DEMO"],
        r1="Ravi, how did you get 45? Can you tell me?",
        r2="Ravi, can you show me with sticks?",
    ),
    "A5_m_hi_hinglish": dict(
        lang="hi",
        gh="शिक्षक",
        names=["सुनील"],
        consent=["agree"],
        arp=["DEMO"],
        r1="Ravi, tum ne 45 kaise nikala? batao",
        r2="ek bundle me 10 sticks hote hain",
    ),
    "A6_f_hi_oneword": dict(
        lang="hi",
        gh="शिक्षिका",
        names=["रिया"],
        consent=["agree"],
        arp=["DEMO"],
        r1="क्यों?",
        r2="😀👍🙏",
    ),
    "A7_m_hi_long": dict(
        lang="hi",
        gh="शिक्षक",
        names=["सुनील"],
        consent=["agree"],
        arp=["DEMO"],
        r1=LONG,
        r2="रवि, तुम 45 कैसे आए?",
    ),
    "A8_f_en_english": dict(
        lang="en",
        gh="Teacher (she)",
        names=["Riya"],
        consent=["agree"],
        arp=["DEMO"],
        r1="Ravi, please explain how you subtracted.",
        r2="Good. Now try 43 minus 27 with bundles and sticks.",
    ),
}
for k, v in variants.items():
    s = [["login", "teacher.demo1"], ["logout"], ["goto", "/login"], ["lang", v["lang"]]]
    s += [
        ["login", "teacher.demo1"],
        ["css", "#start-go"],
        ["say", "Hello" if v["lang"] == "en" else "नमस्ते"],
    ]
    for c in v["consent"]:
        if c == "No_typed":
            s += [["say", "No"], ["say", "नमस्ते"]]
        elif c == "learn":
            s += [["click", "Learn more" if v["lang"] == "en" else "और जानें"]]
        elif c == "agree":
            s += [["click", "I agree" if v["lang"] == "en" else "सहमत हूँ"]]
    for a in v["arp"]:
        s.append(["say", {"bad": "XYZ123", "no": "नहीं" if v["lang"] == "hi" else "no"}.get(a, a)])
    for n in v["names"]:
        s.append(["say", n])
    s.append(["click", v["gh"]])
    s += [
        ["say", "2-5 साल" if v["lang"] == "hi" else "2-5 years"],
        ["say", "कक्षा 2" if v["lang"] == "hi" else "Class 2"],
        ["say", v["r1"]],
        ["say", v["r2"]],
        ["dump"],
    ]
    (out / f"{k}.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
print(list(variants))
