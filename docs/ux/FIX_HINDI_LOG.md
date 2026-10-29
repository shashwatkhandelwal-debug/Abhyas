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
