# Lane A Progress (Core IP: Rule Engine, Hindi Utils, Bug Rules)

Branch: `lane-a`
Worktree: `../abhyas-a`
Port: 8001
Database: None required (pure deterministic algorithms)

## Tasks
- [x] T05 Hindi utilities (llm/hindi_numbers.py, guards.norm, rule_engine/bugs/akshar.py)
- [x] T06 Bug rules (all 12 rules, step templates, registry)
- [x] T07 Rule engine (types, transitions, RuleEngine.step, placement, 100% line coverage)

## Deviations from spec
None.

## Self-Reviews
- T05: Implemented `hindi_numbers.py` (extract_numbers for Arabic/Devanagari/words/Hinglish, to_words 0-199 with exhaustive 0-100 tests), `guards.norm` and `substring_match` with rapidfuzz, and `bugs/akshar.py` with standalone regex matching all spec test cases (किताब, गुड़िया, विद्यालय, आम, संतरा). All 217 tests in test_hindi_numbers and test_akshar pass; ruff and mypy strict clean.
- T06: Implemented all 12 procedural bug rules across subtraction (3), addition (3), place value (3), and literacy (3) plus 4 paired correct functions, step templates, and registry. Every single cell in spec/04 §4.2 tables verified with 59 parametrised unit tests in `test_bugs.py`. Ruff and mypy strict clean.
- T07: Implemented `RuleEngine.step` in strict accordance with spec/04 §4.4 (11-step pipeline + placement mode). Fully implemented `transitions.py` (ADVANCE table and NON_ADVANCING set), `domain.py` schemas (Problem, ChildRuntime, SceneState, TaggedTurn, ChildResponse, StepResult), and backward-compatible re-exports. Created comprehensive test suites: all 14 tests in spec/04 §4.5 passing in `test_rule_engine.py` (Ravi worked example, tell relapse, partial relapse, ineffective acts, shy/scold, priority selection, interjection, whole-class concrete, determinism, property-based non-advancing fuzz test, scene end, literacy reading, serialization), plus complete branch tests in `test_rule_engine_coverage.py`. Reached 100% line coverage across all modules in `rule_engine/` (710/710 statements). All 342 unit tests pass, ruff check clean, ruff format clean, mypy --strict clean.



