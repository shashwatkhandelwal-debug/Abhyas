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

## Deviations from spec
None.

## Self-Reviews
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





