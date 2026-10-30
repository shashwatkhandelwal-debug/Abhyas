# Flow fix log (branch fix/flow-help-name-dash)

## F1 Follow-up flow: DONE
- Follow-up now opens with a lead-in from the stored check-in (module, outcome): catalog keys `fu_ask_leadin`, `fu_leadin_*` (hi, en). Falls back to the old `fu_ask` when no check-in is stored.
- `offer_followup` skips when she has already spoken in the scene, or already answered a follow-up today (IST). Not marked offered in the first case, so it still shows after the scene.
- Every answer ends with a next step: in a scene, a line with the board problem and a `[btn_fu_back]` button; otherwise the existing buttons, or `fu_next_idle` with progress and check-in buttons.
- Deviation: when a scene was opened earlier but she has not spoken, the follow-up is the newest message in the thread (it is not re-ordered before the old scene prompt). The demo teachers start with an empty thread, so there it is first.
- Gate run: ruff, mypy --strict, test_flow_followup, test_followup, test_class_checkin, test_messages_en, test_wording_polish (235 passed), check_first_load (first-load 130226 bytes, PASS; static files untouched).
- `scripts/check_first_load.py` rewrites eval/lowband/REPORT.md on each run; that file is deliberately not committed.

## F2 Questions to the app never go to the child: DONE
- `backend/app/core/help_question.py`: deterministic matcher (NFC, lower case, punctuation stripped, chandrabindu and nukta folded, whole-line match against a phrase list plus a difflib typo tolerance). Says no when the line has a digit, a child name (रवि/प्रिया/अमन, ravi/priya/aman) or an imperative/second-person word (करो, करोगे, घटाओ, बताओ, तुम ...) or is longer than `HELP_QUESTION_MAX_WORDS`. Tunables in config.py.
- `SessionService._help_reply` runs before the check-in, level sorter, follow-up and onboarding handlers (text only). Reuses `web/next_action.py` for the hint, speaker `coach`, plus the scene stop line `help_scene_stop` in a scene, plus quick-reply buttons for learn/model/feedback/done and the address step. No state is written.
- Not intercepted (the line is a free answer there): NEW onboarding, delete confirm, handbook ASK state, rating comment, class/skill free-text asks.
- Gate run: ruff, mypy --strict, test_help_question (48 tests), test_flow_followup, test_messages_en, test_next_action, test_intents, test_placeholder_leaks.

## F3 Name extraction: DONE
- `backend/app/core/name_extract.py` `extract_name(text, lang)`; used by the onboarding state machine. Not a name (long sentence with no frame, digits, markup) means nothing is stored and `ask_name_again` is sent (hi and en).
- SessionService mock, input "मेरा नाम रिया है।" at PROFILE_NAME:
  - before: `STORED NAME: 'मेरा नाम रिया है।'`, then `आपको कैसे संबोधित करें? [शिक्षिका] [शिक्षक]`
  - after:  `STORED NAME: 'रिया'`, then `आपको कैसे संबोधित करें? [शिक्षिका] [शिक्षक]`
  (the "before" run was on the code of the V3 worktree, which has the same name step as main)
- Escaping: no template uses `|safe` on a name (test), Jinja autoescapes the rest, and markup is refused at entry.
- `test_state_machine` edge test now feeds a real name for the `name_text` edge (the literal token is not a name).
- Known, not caused by this change: `test_full_happy_path_new_to_done_with_session_service_and_db_evidence` fails when run alone against the local DB (scene FK warnings, 0 counted turns); it also fails on the untouched V3 worktree. It is checked again in the final gate through `scripts/pytest_fresh_db.py`.
- Gate run: ruff, mypy --strict, test_name_extract (46 tests), test_state_machine (other tests pass), test_teacher_address, test_conversation, test_messages_en, test_whatsapp_channel, test_placeholder_leaks.
