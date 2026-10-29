# Fix Hindi polish: log

Branch `fix/hindi-polish`, cut from `main` (RUN_REPORT_M2.md present).

## F1: coach feedback accuracy: DONE

- The line comes from `content/messages_hi.yaml` key `coach_outcome_relapse`. `backend/app/sessions/outcome.py` selects it whenever the rule engine recorded a `ResponseKind.RELAPSE`. That kind is set in `rule_engine/engine.py` when a PARTIAL child meets a new item with no effective act, and it does not depend on a tell-answer.
- Fix: `outcome_line` now checks the turn acts. The old line is used only if a `tell_answer` act happened in or before the relapse turn. Otherwise the new key `coach_outcome_relapse_scaffold` (Hindi and English) is used. The rule engine is untouched.
- Tests: `backend/tests/unit/test_coach_outcome_relapse.py` (Hindi and English, plus two real SessionService mock-path transcripts).
- Real SessionService mock-path output, first line of the feedback:
  - tell answer, then new problem (PARROT, so the "told" line wins by priority):
    `आपने रवि को उत्तर बता दिया, इसलिए उसने बिना समझे उसे दोहरा दिया। पहले उससे समझाने को कहकर देखें।`
  - explain, bundles, then new problem (relapse, no tell-answer):
    `नए सवाल पर रवि की पुरानी गलती फिर लौट आई। उससे फिर चीज़ें हाथ में लेकर समझाने को कहें।`
- Quick gate: ruff, mypy --strict, the coach outcome tests (13 passed) and check_first_load (127.33 KB first load) all passed.

## F2: strip label: DONE

- `backend/app/rehearsal/header.py` `child_strip_label`: when the relapse marker applies (bug answer after PARTIAL, or told-then-stuck), the label is now "अटका हुआ · फिर अटका" (English "Stuck · Stuck again"), never "समझ रहा है". No engine change; the catalog is unchanged because the stuck and relapse keys already existed.
- Tests: `test_header.py` (bundles-then-relapse exact label; told-then-stuck also asserts no "learning"). 66 passed with `test_one_on_one_flow.py`.
- Screenshots at 393x852, dark and light: `docs/ux/v2/F2-393x852-dark-strip_relapse.png` and `docs/ux/v2/F2-393x852-light-strip_relapse.png`. They come from `scripts/composer_layout_check.py`, whose relapse fixture label I updated to match. The dark one was viewed and shows "रवि · अटका हुआ · फिर अटका"; the light one was captured but not viewed.
- Quick gate: ruff, mypy --strict and check_first_load passed.

## F3: cluster pack wording: DONE

- New catalog key `ui_pack_row` (Hindi and English). Each pack row now reads "<struggle>: बच्चे अटकते हैं, N शिक्षकों ने बताया" ("<struggle>: children get stuck, reported by N teachers"). It is used in `_cluster_pack.html`.
- The agenda share line (`ui_pack_agenda_share`) now says teachers reported where children get stuck. All agenda lines were already catalog strings with English twins, so none are hard-coded.
- Asterisks: I found no markdown asterisks in `class_struggles.yaml`, the pack templates or the catalog strings, so I could not reproduce the problem from source. As a safeguard, `cluster_pack._plain` strips `*` from the stored label and tip before display, and the tests assert the rendered card and print page contain none.
- Tests, added to `test_cluster_pack_postgres.py`: row text in Hindi and English, the agenda without asterisks, and suppression at 9 teachers versus display at 10. On a fresh local database, 42 passed together with `test_arp_digest.py`.
- Quick gate: ruff, mypy --strict and check_first_load passed.

## F4: regrouping tip relevance and terminology: DONE (no change needed)

(a) Chunk ids mapped to `NUM_SUB_REGROUP` in `content/class_struggles.yaml`:

| chunk id | Hindi summary (`gloss_hi`) | Addresses regrouping or bundles? |
|---|---|---|
| `nipun_guidelines_2021:p283:284` | "यह अंश कक्षा 3 के गणित की योग्यताओं का विवरण है, जिसमें दो और तीन अंकों की संख्याओं, जोड़, घटाव, संबंध, गुणा और भाग की समझ और उनके दैनिक जीवन में उपयोग शामिल हैं।" | No. It is a Class 3 competency table that mentions "develops their own strategies to add". |
| `nishtha_fln:p439:316` | "यह अंश बच्चों में संख्या और संक्रियाओं (जोड़, घटाना आदि) की समझ विकसित करने के तरीके बताता है, ताकि वे इन्हें रोज़मर्रा की समस्याएँ हल करने में उपयोग कर सकें।" | No. It covers subtraction as take-away/left-over, which is what the current tip paraphrases. It does not cover regrouping. |

I searched all 1,157 stored chunks for बंडल, दहाई, उधार, हासिल, खोलना and the English borrow/regroup/exchange/unbundle:
- The only बंडल hits in handbook text are in `up_ganit_sandarshika_c1`. They are place-value and writing-numbers material: p063:102 (how many bundles and loose sticks for 43) and p089:143 (making sticks and bundles from local materials). They are about bundles but not about opening one in subtraction.
- "regrouping" appears in `nipun_guidelines_2021` p142:140 (grouping to understand things) and p284:285 (a money row, "with or without regrouping"). Neither is about subtraction with borrowing.
- Nothing clearly fits better, so I kept the mapping and swapped nothing. The tip text stays as it was.

(b) Terminology counts of "हासिल" and "उधार" in the stored handbook chunks (text, `gloss_hi`, heading and keywords):

| source | हासिल | उधार |
|---|---|---|
| ncert_vidya_pravesh | 0 | 0 |
| nipun_guidelines_2021 | 1 | 0 |
| nishtha_fln | 0 | 0 |
| up_bhasha_sandarshika_c1 | 0 | 0 |
| up_ganit_sandarshika_c1 | 4 | 0 |

- The one hit in nipun is "हासिल" in the sense of "achieve" (p104:099), not carrying.
- The 4 hits listed under `up_ganit_sandarshika_c1` are rows with ids like `NUM_*_BUNDLES_learn`, which are our own move-card rows indexed under that source, not handbook text. I confirmed this from their chunk ids.
- So the handbooks use no consistent term for borrowing or carry. "उधार" never appears, and "हासिल" appears in handbook text only as "achieve". There is no different handbook term to switch to, so I left the label, which is catalog and yaml text, unchanged.
- Open question for a human: "हासिल वाला घटाव" borrows the addition-carry word for subtraction. A Hindi-speaking teacher should confirm whether it reads naturally.
