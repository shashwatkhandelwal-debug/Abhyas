# Run report 3

Branch `feature/hackathon-polish`. No real Anthropic key; the Claude API was not called. Everything below was run this
session unless marked **assumed**.

Commits (each `git show --stat` was pasted in the session):

| Commit | Subject |
|---|---|
| `265233d` | build Fast-Track chip B from the current board; disable when no regroup or no subtraction |
| `0260cd4` | Fix Hindi word order in explain_back_reply and fidelity_reply_summary |
| `407cded` | Coach outcome line: literacy scenes get neutral wording, not bundles and sticks |

## Task 1: Chip B from the current board

`getChipBText(sc)` in `backend/app/web/static/chat.js` builds the text from the board problem. It shares a new
`getSubItem()` with `getChipA1Text`: the scene's `item` when it is a subtraction, otherwise the `sb-board` text. It
returns `null` (chip disabled) when there is no subtraction item or `units(a) >= units(b)`. Unicode escapes are kept.
The static 43-27 default in `setupFastTrackTray` is removed. `updateFastTrackChips` and `enableFastTrackChips` now treat
chip B like A1: dynamic text, disabled when null.

JS tests (`chat.test.mjs`, new test "chip B text is built from the current board…"):

| Board | Result |
|---|---|
| 43-27 | `चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।` |
| 61-28 | `चलो 61 में से 28 फिर से करते हैं: देखो, 6 बंडल और 1 खुली तीलियाँ हैं, 1 में से 8 नहीं निकलतीं, तो एक बंडल खोलो।` |
| 80-35 | `चलो 80 में से 35 फिर से करते हैं: देखो, 8 बंडल और 0 खुली तीलियाँ हैं, 0 में से 5 नहीं निकलतीं, तो एक बंडल खोलो।` |
| 58-23, a literacy item, no scene | `null`, chip disabled, `data-text` removed |

Python test `test_fast_track_a2_then_b_when_tagger_returns_no_problem` wraps `scene_runner.tag_act` so it returns
`problem=None` for chip B's text (the Claude behaviour). A2 is left untouched. Sequence and final state, from a debug
run of the same steps:

```
A2  acts [give_new_problem]  board sub:61-28   ravi: ... तो उत्तर 47 है!
B   acts [concrete_representation, model_step_aloud]  tagger problem=None (nulled)
    board sub:61-28   ravi: ... 11 में से 8 घटाया, 3 आया। 5 में से 2 घटाया, 3 आया। तो उत्तर 33!
```

The board, the teacher line (61/28, 6 bundles) and Ravi's answer (33) all agree. The test asserts that 43/27 and 16
appear nowhere.

- **Not re-run for the old behaviour:** the "before" case (old chip B text, board 61-28, teacher line about 43/27) comes
  from the task description and from reading the old code. I did not re-run it against the old text.
- **Old permutation tests unchanged:** the three existing permutation tests and the repeat-taps test still use the old
  43-27 chip B string as a literal transcript. They pass and still cover the fallback tagger path. I did not rewrite them.
- **Hindi word order in the B text:** "1 में से 8 नहीं निकलतीं" follows the string you specified. It is the existing
  chip B phrasing and reads as "8 can't be taken from 1".

Payload (`scripts/check_first_load.py`; limit 153,600 B; this CRLF machine overstates by 2,292 B, so LF-equivalent
headroom = measured + 2,292):

| | All offline assets, CRLF headroom | LF-equivalent headroom | Teacher first-load, CRLF headroom |
|---|---|---|---|
| before | 1,968 B | 4,260 B | 23,105 B |
| after | 1,810 B | 4,102 B | 22,947 B |

The change costs 158 B. LF-equivalent headroom stays above the 1,000 B floor. The measurement helper was a scratch
script outside the repo that calls `measure_first_load`. `eval/lowband/REPORT.md` was rewritten by the script and is not
committed.

## Task 2: Hindi word order

Placeholder meanings, verified in code:

- `fidelity_reply_summary` is the live path. `compose_fidelity_reply` (`backend/app/llm/roles/fidelity_checker.py`)
  fills it with `n_covered` (key points with status `covered`) and `n_total` (`len(move.key_points)`).
- `explain_back_reply` has `{covered}`/`{total}` and is listed in the state machine's `message_keys`. I found no code
  that renders it: `service.py` uses `fidelity_res.reply_hi`. It is a latent duplicate and is fixed too.

| | Rendered (covered=2, total=3) |
|---|---|
| before | `धन्यवाद! आपने 2 में से 3 मुख्य बातें कहीं।` |
| after | `धन्यवाद! आपने 3 में से 2 मुख्य बातें कहीं।` |

Both keys were changed to "{total} में से {covered}" in `content/messages_hi.yaml`. The same change went into
`content-seed/messages_hi.yaml` and the docstring in `fidelity_checker.py`. `test_messages_loader.py` pinned the old
string and now pins the new one. A new test covers both keys. `test_compose_fidelity_reply_all_covered` is symmetric
(n/n), so it did not catch the bug and is unchanged.

## Task 3: Literacy feedback wording

| String | File and key | Used by |
|---|---|---|
| `ठोस चीज़ (बंडल और तीलियाँ)` | `content/messages_hi.yaml`, `coach_outcome_concrete` | `backend/app/sessions/outcome.py::outcome_line`, called from `service.py` |
| `अमन की गलती से जुड़ी है` | `content/messages_hi.yaml`, `coach_class_link` | `service.py`, via `personalise.focus_child` |

**Not mock-only.** `outcome_line` is built only from the tagged acts and the engine's recorded `ResponseKind`s, with no
model call. It runs for every scene on every provider. It chose `coach_outcome_concrete` for any
`SCAFFOLDED_CORRECT` response, whatever the move's domain. In `engine.py` that kind is emitted for literacy PARTIAL
children as well. The bundle wording could therefore reach a literacy scene on the real path, and it does not depend on
the coach LLM or its fallbacks.

The coach fallbacks (`fallback_coach_feedback`, used for token budget, guard failure and API error) take their text from
the move's own `feedback_bank` plus `coach_fallback_neutral`. `grep -c "बंडल\|तीली" content/moves/LIT_MATRA_BLENDING.yaml`
returned 0, and `coach_fallback_neutral` is neutral. No other real-path fallback emits bundle wording for literacy.

Fix:

- `outcome_line` takes an optional `domain`. For `Domain.LITERACY`, `coach_outcome_concrete` maps to the new key
  `coach_outcome_concrete_literacy`.
- `service.py` passes `move.domain`.
- Hindi text: `आपकी मदद से {child} ने शब्द सही पढ़ा: ध्वनि को पकड़ने में उसे सहारा मिला।`
- English text added too.
- Numeracy and callers that pass no domain are unchanged.
- Test: `test_a_literacy_scene_never_gets_the_bundles_and_sticks_wording`.

`coach_class_link` ("…{child} की गलती से जुड़ी है") is generic. It says "ठोस चीज़ों" without bundles. It only appears when
the class profile has a matching struggle, so it did not appear in the run below. I left it unchanged.

Full literacy scene, group mode, mocks, driven through `SessionService` with an empty API key (`LIT_MATRA_BLENDING`,
turns as in run report 2):

```
TEACHER: प्रिया, बोर्ड पर क्या लिखा है? पढ़ो।
  [priya] मछली!
TEACHER: प्रिया, म पर ए की मात्रा 'मे' और ल पर आ की मात्रा 'ला', मिलाकर पढ़ो।
  [priya] हम्म… मे - ला। मेला!
TEACHER: प्रिया, बहुत बढ़िया! अब पूरा शब्द मिलाकर फिर से पढ़ो।
  [priya] हम्म… मे - ला। मेला!   [aman] दीदी, आज मिड-डे मील में क्या है?
TEACHER: बस
  [coach] चलिए, अब फीडबैक देखते हैं।
  आपके अभ्यास पर सुझाव:
  आपकी मदद से प्रिया ने शब्द सही पढ़ा: ध्वनि को पकड़ने में उसे सहारा मिला।

  (यह सुझाव एक विशेषज्ञ भी देखेंगे।)

  👍 आपने अक्षर और मात्रा की ध्वनि अलग-अलग बुलवाई।
  🔁 शब्द पढ़कर सुनाने से पहले धीरे-धीरे ध्वनियाँ मिलाकर दिखाइए, फिर बच्चों से साथ में करवाइए।
  🗣️ अगली बार ऐसे कहकर देखें: "दोनों के पढ़े शब्द सुनो, अक्षर मिलाकर बताओ कि कौन-सा सही है?"
```

Aman's mock line about mid-day meal is the mock child-voice behaviour, as in report 2.

## Final checks

- Full pytest, `python -m pytest -o addopts="" --tb=short`: **1569 passed, 129 skipped in 173.17s**. The skips are
  `TEST_DATABASE_URL`, audio samples and similar. The earlier two pytest runs this session did not show a summary line
  (the repo's addopts hide it), so the suite was run three times. Only the last result is quoted.
- Node chat tests, `node --test backend/tests/js/chat.test.mjs`: **tests 66, pass 66, fail 0**. Before that I ran the
  same file once, filtered to the Fast-Track test names, to check the new test.
- `mypy --strict backend/app`: no issues in 169 source files. `ruff check backend`: clean. `ruff format --check` was run
  on the touched Python files.
- CI was not run (**assumed green**). The git push rule applies, so nothing was pushed.

## Not done and assumed

- Chip B against the real Claude tagger. The Claude path is simulated by forcing `problem=None`; real tagger output for
  the new text is untested because no key was available.
- Old-text before/after run for chip B (see above).
- Browser check of the tray. Behaviour is covered only by the Node DOM stub tests.
- `eval/lowband/REPORT.md` shows as modified (script noise) and was deliberately not committed.
