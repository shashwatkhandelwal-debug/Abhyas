# Track B log

Branch `feat/track-b` (worktree `Abhyas-trackb`), from main 81a2f41. Decisions and per-task notes, newest last.
The other session works on `fix/flow-help-name-dash`, which merges into main first.

## Files each task touches (and likely overlap with fix/flow-help-name-dash)

| Task | Files | Overlap risk |
|---|---|---|
| T1, T2 scenes | `rule_engine/domain.py`, `engine.py`, `bugs/compare.py` (new), `bugs/letter_sound.py` (new), `bugs/templates.py`, `bugs/__init__.py`, `llm/roles/act_tagger.py`, `rehearsal/header.py`, `web/next_action.py`, `config.py`, `class_profile/library.py`, `class_profile/checkin_flow.py`, `sessions/path.py`, `reports/trainer_aggregates.py`, `content/moves/*` (2 new), `content-seed/moves/*`, `content/class_struggles.yaml`, `content/messages_hi.yaml`, `content/messages_en.yaml` (appended at the end), `content/pipeline/validator.py` | catalogs (append-only block `# Track B scenes`); `class_struggles.yaml` (two entries rewired) |
| T3 training gap | `reports/training_gap.py` (new), `reports/trainer_view.py`, `web/trainer.py`, `templates/trainer.html` or a new partial, `db/demo_data.py` or `seed.py` | trainer template and CSV download (other branch) |
| T4 focus card | `class_profile/focus.py` (new), `sessions/service.py` (one hook), `sessions/state_machine.py` (ctx fields), catalogs, `db/seed.py` | `sessions/service.py` (follow-up flow lives there), catalogs |
| T5 fast start | `sessions/service.py` (learn buttons), `sessions/state_machine.py`, catalogs, progress mark | `sessions/service.py`, catalogs |
| T6 audio | `sessions/service.py` (model-practice message), `speech/*` read only | `sessions/service.py` |

Merge advice: catalogs are append-only at the end of each file, so a textual conflict is resolved by keeping both blocks.
`sessions/service.py` hooks are small and each is marked with the flag name.

## Decisions

- **Time check**: started 10:57 IST on 30 Oct 2026. Environment: `backend.app.config` resolves inside this worktree, no PYTHONPATH needed.
- **Flag semantics**: every Track B flag is "flag or DEMO_MODE" (`v2_enabled`), as the V2/V3 flags. Tests that prove "flags off" set `DEMO_MODE=False` and the flag `False`.
- **Gating of the two scenes**: the move cards exist on disk always (content tests, review console and the move table read them). What the flag gates is the offer: `config.FLAGGED_MOVES` and `move_offered()`. With the flag off, `load_library()` returns the struggle with `move_id: null` and no `misconception_ids` (the library as on main), so the check-in offers no practice. The weekly path (`compute_move_path`) and the trainer module table never include the two Track B moves in any mode (they are on-demand practice, and demo counts stay unchanged).
- **T1 misconception**: one rule, `CMP_ONES_FIRST`. All three children use it (the scene differs by temperament only). Rule works for any pair incl. one-digit vs two-digit and equal numbers; when the ones digits agree with the tens (42 vs 47) or are equal, the bug does not show and the correct answer is returned (same convention as the subtraction rules).
- **T1 board**: text only, "39 और 41: कौन बड़ा?". The bundles-and-sticks drawing takes one number (`manipulatives`), not two, and `chat.js` may not change.
- **T1 teacher-posed pairs**: allowed 1..99 via `COMPARE_MIN_OPERAND` (the existing 10..99 limit would reject one-digit numbers). The keyword tagger reads "28 और 33, कौन बड़ा?" as a new pair only when the pair differs from the board and there is a cue word (कौन, बड़ा, तुलना, नया सवाल...) or both numbers are two-digit.
- **T2 misconception**: the stored chunks (all six sources searched for similar-letter pairs, confusion, मिलते-जुलते, ब/व) name no confusable pair. As instructed, the scene uses letter name versus letter sound (NIPUN glossary p004:001: letters have specific names and specific sounds). The child gives the alphabet-chart name, "ब से बतख", instead of sounding the word. Rule `LETTER_NAME_FOR_SOUND`, chart words in `bugs/letter_sound.py`. The scene is group only, like the matra scene (no one-on-one rubric needed for literacy).
- **T2 sound-out to CORRECT**: the existing transition table moves PHONICS_SOUND_OUT to PARTIAL only; PARTIAL to CORRECT needs a model-step-aloud or contrast act (same as the matra scene). Existing rules were not changed.
- **Pre-existing tagger quirk (not changed)**: the keyword tagger reads the word after "शब्द" as the new word to read, so "तुमने यह शब्द कैसे पढ़ा?" poses the word "कैसे". It affects the matra scene too. Test lines avoid "शब्द" unless a word follows.
- **Content honesty**: only key points that paraphrase a stored chunk carry `source_chunk_ids` (NUM_COMPARE: up_ganit_sandarshika_c1 p041:060, p109:166, p030:039; LIT_LETTER_SOUND: nipun p004:001, p074:068, ncert_vidya_pravesh p032:031). The "count the bundles first" step and the letter-name framing are the team's own scene design and say so in the card header. `module_ref.page` is null and `verified: false`, as on the other cards. `content/chunks/seed_from_moves.jsonl` (retrieval seed derived from cards) was not regenerated.
- **T1 and T2 share one commit** because they share config, templates, validator and tests.
- **Older tests adjusted** (not behaviour): `test_bugs` registry size counts the original 12 plus the two scene rules; `test_coach`, `test_fidelity_checker`, `test_content_pipeline` cover six seed moves; `test_class_checkin` pins the library to flags-off (it asserts exact module buttons).
- **Addendum T5b received** (support framing, observation to teacher, no scores for non-opted-in teachers, school context, pitch notes). It is done after T5 and before T6.
