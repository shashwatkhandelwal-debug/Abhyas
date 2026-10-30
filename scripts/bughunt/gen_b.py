# ruff: noqa
"""Generate journey B (rehearsals) files. Short on purpose: live-call budget is 400 for the whole run."""

import json, pathlib

out = pathlib.Path(__file__).parent / "journeys"
EXPL = "बच्चे से पूछें कि उसने कैसे किया, फिर बंडल और तीलियों से संख्या बनवाएँ और जरूरत हो तो एक बंडल खोलें।"


def setup(module, child, user="teacher.demo3"):
    return [
        ["login", user],
        ["logout"],
        ["login", user],
        ["css", "#start-skip"],
        ["module", module],
        ["click", "आगे"],
        ["say", EXPL],
        ["click", "छोड़ें"],
        ["click", "1-1 बच्चे से बात"],
        ["click", child],
        ["dump"],
        ["click", "छोड़ें"],
    ]


J = {}
J["B_sub_ravi"] = setup("NUM_SUB_REGROUP_BUNDLES", "रवि") + [
    ["say", "रवि, तुमने यह कैसे किया? बताओ।"],
    ["say", "रवि, बंडल और तीलियाँ लेकर बनाओ। 3 तीलियों में से 7 कैसे निकालोगे?"],
    ["say", "ऊपर 43 नीचे 27 लिखो, 13 में से 7 घटाओ, 3 में से 2 घटाओ, अब बताओ जवाब क्या है"],
    ["say", "ऊपर 43 नीचे 27 लिखो, 13 में से 7 घटाओ, 3 में से 2 घटाओ, अब बताओ जवाब क्या है"],
    ["say", "तुम हमेशा गलत करते हो, ध्यान से सुनो!"],
    ["say", "आज बाहर बारिश हो रही है न?"],
    ["say", "अब एक नया सवाल: 52 − 38 बंडल लेकर करके देखो।"],
    ["say", "अब क्या करूँ"],
    ["say", "बस"],
]
J["B_sub_priya"] = setup("NUM_SUB_REGROUP_BUNDLES", "प्रिया") + [
    ["say", "प्रिया, तुमने कैसे सोचा? बताओ।"],
    ["say", "प्रिया, 10 तीलियों का एक बंडल बनाकर दिखाओ, फिर घटाओ।"],
    ["say", "प्रिया, जवाब 16 है। समझ गईं?"],
    ["say", "प्रिया, ज़रा फिर से बताओ, तुम्हारा तरीका क्या था?"],
    ["say", "Priya, can you show me with sticks?"],
    ["say", "बस"],
]
J["B_sub_aman"] = setup("NUM_SUB_REGROUP_BUNDLES", "अमन") + [
    ["say", "अमन, तुमने कैसे किया?"],
    ["say", "अमन, बंडल और तीलियों से 43 बनाओ और उनमें से 27 हटाकर दिखाओ।"],
    ["say", "अमन, यह ठीक नहीं है। मैं बताता हूँ: जवाब 16 है।"],
    ["say", "अमन, क्या तुम एक नया सवाल कर सकते हो: 61 − 24?"],
    ["sheet"],
    ["closesheet"],
    ["say", "बस"],
]
J["B_compare"] = setup("NUM_COMPARE_BUNDLES", "रवि") + [
    ["say", "तुमने कैसे तय किया कि कौन-सी संख्या बड़ी है?"],
    ["say", "बंडल और तीलियों से दोनों संख्याएँ बनाकर देखो।"],
    ["say", "पहले दहाई के अंक देखो, कौन-सा बड़ा है?"],
    ["say", "बस"],
]
J["B_letter"] = setup("LIT_LETTER_SOUND_PAIRS", "रवि") + [
    ["say", "तुमने यह अक्षर कैसे पहचाना? बताओ।"],
    ["say", "इसकी ध्वनि अपने मुँह से बोलकर दिखाओ, फिर दोनों अक्षरों की तुलना करो।"],
    ["say", "ये दोनों अक्षर अलग हैं, पहला क, दूसरा ख। अब बताओ।"],
    ["say", "बस"],
]
for k, v in J.items():
    (out / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
print(list(J))
