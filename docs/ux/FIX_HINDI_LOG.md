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
