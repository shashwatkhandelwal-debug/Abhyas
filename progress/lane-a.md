# Lane A Progress (Core IP: Rule Engine, Hindi Utils, Bug Rules)

Branch: `lane-a`
Worktree: `../abhyas-a`
Port: 8001
Database: None required (pure deterministic algorithms)

## Tasks
- [x] T05 Hindi utilities (llm/hindi_numbers.py, guards.norm, rule_engine/bugs/akshar.py)
- [ ] T06 Bug rules (all 12 rules, step templates, registry)
- [ ] T07 Rule engine (types, transitions, RuleEngine.step, placement, 100% line coverage)

## Deviations from spec
None.

## Self-Reviews
- T05: Implemented `hindi_numbers.py` (extract_numbers for Arabic/Devanagari/words/Hinglish, to_words 0-199 with exhaustive 0-100 tests), `guards.norm` and `substring_match` with rapidfuzz, and `bugs/akshar.py` with standalone regex matching all spec test cases (किताब, गुड़िया, विद्यालय, आम, संतरा). All 217 tests in test_hindi_numbers and test_akshar pass; ruff and mypy strict clean.

