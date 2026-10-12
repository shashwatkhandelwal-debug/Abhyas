# Lane A Progress (Core IP: Rule Engine, Hindi Utils, Bug Rules)

Branch: `lane-a`
Worktree: `../abhyas-a`
Port: 8001
Database: None required (pure deterministic algorithms)

## Tasks
- [x] T05 Hindi utilities (llm/hindi_numbers.py, guards.norm, rule_engine/bugs/akshar.py)
- [x] T06 Bug rules (all 12 rules, step templates, registry)
- [x] T07 Rule engine (types, transitions, RuleEngine.step, placement, 100% line coverage)
- [x] T09 Guards (all 8 spec/05 guards, >= 3 pass/fail fixtures, 97% line coverage)
- [x] T10 act_tagger (P0: prompt v1, content/act_examples_hi.yaml with 28 examples, keyword fallback, 8 golden fixtures, labelled dataset, 100% line coverage)
- [x] T11 child_voice (P0: prompt v1, guard wiring, retry-once + template fallback, 20 golden good/bad fixtures across all 10 kinds, live guard pass >= 90% on rule engine outputs)
- [x] T12 coach (P0: prompt v1, guard_coach enforcement, retry-once + feedback bank fallback, all 4 seed moves verification, review item creation)

## Deviations from spec
- T12 coach fallback: If any negative act from a criterion's `negative_acts` (e.g. `tell_answer`) occurred in teacher turns, that criterion is scored 0 with evidence `""`. While not explicitly specified in spec/05 §5.6, this prevents rewarding ineffective teaching acts and enforces pedagogical alignment.

## Self-Reviews
- Fix Forward Items 1-8:
  1. `hindi_numbers` / `guard_child_line`: Disambiguated "दो" (verb 'give' vs number 2). "दो" counts as a number only when next to another number or before a counting noun (बंडल, तीली, तीलियाँ, बच्चे, etc.); otherwise ignored. Verified with tests ("दीदी, मुझे तीली दो ना" → [], "दो बंडल" → [2], "नौ दो ग्यारह" → [9, 2, 11]).
  2. `guard_child_line`: Out-of-character terms match whole words via regex `\b` for Latin (ai, assistant, rule, misconception) and Devanagari word tokens (गलती, नियम). Substrings like 'email' pass cleanly.
  3. `TELL_ANSWER` fallback: Requires stated answer, filtering out questions ("रवि, सही उत्तर क्या है?" does not trigger tell_answer; "Ravi, answer 16 hai" triggers tell_answer).
  4. `SCOLD` fallback: Removed neutral "ध्यान दो" from scold pattern; preserved "चुप रहो", "चुपचाप", "इतना भी नहीं आता", "गलत है ना".
  5. Problem detection in fallback: Subtraction phrases ("X में से Y", "X - Y", "X माइनस Y", "X से Y घटाओ"), addition phrases ("X और Y जोड़ो", "X + Y", "X प्लस Y"), place value ("X बंडल और Y तीलियाँ"), and literacy words ("शब्द X", "X पढ़ो"), validated against `current_item.type` before setting problem.
  6. "all" detection: Matched as whole word/phrase (`\b(?:all|everyone)\b` and token-bounded Devanagari phrases).
  7. Deleted legacy prompt modules `backend/app/llm/prompts/*.py`; added versioned template loader `load_prompt` in `backend/app/llm/prompts/__init__.py`.
  8. Added unit tests for items 1-8 and all 5 evaluator samples (s1-s5) in `backend/tests/unit/test_act_tagger.py`.
- T05: Implemented `hindi_numbers.py` (extract_numbers for Arabic/Devanagari/words/Hinglish, to_words 0-199 with exhaustive 0-100 tests), `guards.norm` and `substring_match` with rapidfuzz, and `bugs/akshar.py` with standalone regex matching all spec test cases (किताब, गुड़िया, विद्यालय, आम, संतरा). All 217 tests in test_hindi_numbers and test_akshar pass; ruff and mypy strict clean.
- T06: Implemented all 12 procedural bug rules across subtraction (3), addition (3), place value (3), and literacy (3) plus 4 paired correct functions, step templates, and registry. Every single cell in spec/04 §4.2 tables verified with 59 parametrised unit tests in `test_bugs.py`. Ruff and mypy strict clean.
- T07: Implemented `RuleEngine.step` in strict accordance with spec/04 §4.4 (11-step pipeline + placement mode). Fully implemented `transitions.py` (ADVANCE table and NON_ADVANCING set), `domain.py` schemas (Problem, ChildRuntime, SceneState, TaggedTurn, ChildResponse, StepResult), and backward-compatible re-exports. Created comprehensive test suites: all 14 tests in spec/04 §4.5 passing in `test_rule_engine.py` (Ravi worked example, tell relapse, partial relapse, ineffective acts, shy/scold, priority selection, interjection, whole-class concrete, determinism, property-based non-advancing fuzz test, scene end, literacy reading, serialization), plus complete branch tests in `test_rule_engine_coverage.py`. Reached 100% line coverage across all modules in `rule_engine/` (710/710 statements). All 342 unit tests pass, ruff check clean, ruff format clean, mypy --strict clean.
- Coordinator Review Feedback Fixes:
  1. `sub_correct`: Added missing units subtraction step (`SUB_UNITS_NORMAL`, "13 में से 7 घटाया, 6 आया") on regrouping cases; verified `allowed_numbers` on 43-27 contains 6 and 13.
  2. Non-chaining transitions: Step 4 and Step 6 both compute single-step transitions strictly from start-of-turn child state snapshot (`start_states`), preventing multi-step chaining within one turn.
  3. Turn limit enforcement: Enforced `_check_end_conditions` on all exit paths (including SILENT and CONFUSED returns).
  4. `guess_lexicon`: Added `guess_lexicon: dict[str, list[str]] = Field(default_factory=dict)` to `SceneState` and used directly in answer computation.
  5. Literacy reading: `read_correct` renders `READ_AKSHARS` with aksharas joined by `" - "` and `words=aksharas`.
  6. Cleanup: Deleted `RuleEngineResult`, `RehearsalRuleEngine`, and legacy `TRANSITIONS` in `child_state.py`; eliminated `# type: ignore` in `transitions.py`; moved config tunables to `SceneState` fields (`max_turns`, `shy_silent_turns`, `distracted_interject_after`); simulated all 4 seed model rehearsals through the engine, confirming all 4 moves end in `all_correct`. 100% line coverage maintained (673/673 statements).
- T09: Implemented all 8 Claude output guards matching spec/05 §5.3–§5.10 in `backend/app/llm/guards.py`:
  1. `guard_intent_router`: Schema and intent enum validity + confidence bounds [0.0, 1.0].
  2. `guard_act_tagger`: Taxonomy membership, max 4 acts, persona id / "all" / None address, quote substring match with fuzzy fallback, and problem number/word verification via hindi_numbers.
  3. `guard_child_line`: Length (<= 25 words), silent child empty line, character consistency, off-topic/interject number restriction, allowed numbers enforcement, forbidden token verification (checked prior to answer presence to prevent false-negative messages), and literacy word answer presence.
  4. `guard_coach`: Rubric criteria key and score (0/1/2) integrity, teacher speech extraction and quote verification against teacher turns, word budget (<= 60 words), single-sentence integrity, respectful Hindi register (आप/आपने, no तुम/तुमने), leaked answer detection.
  5. `guard_fidelity_checker`: Key point IDs 1:1 match, covered/partial quote substring matching, missing empty quote enforcement, max 3 misconceptions (<= 25 words each), confidence bounds.
  6. `guard_question_classifier`: Category validity, clarifying question bounds (<= 20 words) when needed, search query presence for pedagogy/classroom management, confidence bounds.
  7. `guard_guide_answerer`: Source IDs non-empty subset of retrieved, max 80 words, cited chunks number verification, respectful register (no तुम/तुमने), confidence bounds.
  8. `guard_page_ocr`: Devanagari character ratio >= 0.60, non-empty text enforcement.
  - Test suite written test-first with >= 3 pass and >= 3 fail fixtures per guard (62 tests total in `test_guards.py`).
  - Achieved 97% line coverage on `backend/app/llm/guards.py` (226/234 statements).
  - All 408 unit tests pass clean. `ruff check` clean, `ruff format` clean, `mypy --strict` clean with zero issues.
- T10: Implemented act_tagger role matching spec/05 §5.4 and T10 acceptance criteria:
  1. Prompt v1 authored in `backend/app/llm/prompts/act_tagger.v1.md` with dynamic slot substitution and worked examples block.
  2. Created `content/act_examples_hi.yaml` with 28 worked examples across all 14 teaching acts (2 per act), including the Ravi worked example.
  3. Implemented deterministic, rule_engine-independent keyword fallback tagger in `backend/app/llm/roles/act_tagger.py` (regex matching, earliest-occurrence child address resolution, and problem number extraction).
  4. Implemented async `tag_act` with spec/05 §5.2 role contract pattern (build_input -> call_tool -> validate -> guard -> retry once on error -> fallback).
  5. Authored 8 golden fixtures conforming to schema in `backend/tests/golden/act_tagger/` (all verified passing guard_act_tagger).
  6. Authored `backend/tests/golden/act_tagger/labelled.jsonl` with 20 labelled teacher turns.
  7. Tested fallback tagger across 16 diverse sentences; achieved 100% line coverage on `act_tagger.py` (98/98 statements).
  8. All 434 tests passing clean. `ruff check` clean, `ruff format` clean, `mypy --strict` clean with zero issues.
- T11: Implemented child_voice role matching spec/05 §5.5 and T11 acceptance criteria:
  1. Authored prompt template `backend/app/llm/prompts/child_voice.v1.md` matching §5.5 verbatim with actor framing, persona cards, affect, kind, and hard rules.
  2. Implemented `voice_child_line` in `backend/app/llm/roles/child_voice.py` strictly implementing spec/05 §5.2 role contract pattern: SILENT kind skips LLM call and returns `""` immediately; non-silent kinds call Claude via `call_tool`, validate against `ChildVoiceOutput`, run `guard_child_line`, retry once with guard failure error message on failure, and fall back to deterministic `template_line` on double failure.
  3. Implemented deterministic `template_line` covering all 10 `ResponseKind`s (ANSWER, EXPLAIN_BUG, SCAFFOLDED_CORRECT, RELAPSE, CORRECT_EXPLAINED, PARROT, SILENT, OFF_TOPIC, INTERJECT, CONFUSED) with `_format_steps` step-budgeting ensuring word count stays strictly <= `MAX_CHILD_LINE_WORDS` (25 words).
  4. Created 20 golden fixtures in `backend/tests/golden/child_voice/` providing both good (passing) and bad (failing) fixtures for every single `ResponseKind`.
  5. Authored comprehensive test suite in `backend/tests/unit/test_child_voice.py`: template fallback for all 10 kinds, golden fixtures verification (all 20 fixtures), role contract with AsyncMock (silent skip, single retry on guard failure, double-failure template fallback), and live guard pass rate verification (42 rule engine responses tested, 100% pass rate >= 90%).
  6. All 453 unit tests pass clean. `ruff check` clean, `ruff format` clean, `mypy --strict` clean with zero issues.
- T12: Implemented coach role matching spec/05 §5.6, T12 acceptance criteria, and coordinator review changes:
  1. Typed inputs: Defined `SceneTurn` and updated `coach_feedback` and `fallback_coach_feedback` signatures with typed `turns: list[SceneTurn]`, `acts: list[list[TeachingAct]]`, `trajectories: dict[str, list[ChildState]]`, `target_child_id: str`, `current_item_answer: int | str`. Removed all string parsing heuristics (`_to_transcript_str`, `_parse_act_tags`, `_check_child_advanced`, `_extract_item_answer`, `_extract_teacher_speech`).
  2. Enforced `len(acts) == len(teacher_turns)` validation, raising `ValueError` on misalignment.
  3. Added progression rank function `child_state_rank` in `rule_engine` (MISCONCEPTION=0 < CAN_EXPLAIN=1 < PARTIAL=2 < CORRECT=3). Advancement requires target child's rank to strictly increase; relapses do not count.
  4. Removed unrelated evidence default (quotes only the exact teacher turn exhibiting the signal act; score 0 with empty quote otherwise).
  5. Kept `CoachFeedbackOutput` strictly matching spec §5.6 without `needs_review`, returning separate `CoachResult(feedback, needs_review, review_reason, used_fallback)`.
  6. Removed all DB imports/writes in `llm/`.
  7. Narrowed exception handling: catches only `LLMUnavailable` (goes directly to fallback without retry), `ValidationError`, and client timeout/HTTP errors; programming errors (e.g. `TypeError`) propagate unswallowed.
  8. Prompt hygiene: system prompt holds instructions and rubric only; transcript, acts, trajectories quarantined inside `<transcript>...</transcript>` tags in user prompt with data delimiter instructions.
  9. Sanitizes answer leaks using localized messages loaded by key from `content/messages_hi.yaml` (`coach_exact_words_contrast_math`, `coach_exact_words_contrast_lit`).
  10. `improved_since_last` is True ONLY when `previous_scores` is given and score on targeted criterion increased.
  11. Documented deviation for negative acts override.
  12. Authored 15 comprehensive unit tests in `backend/tests/unit/test_coach.py`. All 468 unit tests pass clean. `ruff check` clean, `ruff format` clean, `mypy --strict` clean with zero issues.






