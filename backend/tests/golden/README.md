# Golden Test Fixtures

These test fixtures in `backend/tests/golden/` are **hand-written synthetic test cases** crafted to conform to the strict JSON schemas, pedagogical moves, and guardrail specifications defined in `spec/04_rule_engine.md` and `spec/05_llm_roles.md`. They are **not recorded Claude model outputs**.

### Purpose
- **Validation:** Provide regression tests for output schemas, Pydantic models, and safety guards across all runtime roles (`act_tagger`, `child_voice`, `coach`, `fidelity_checker`, `guide_answerer`, `question_classifier`, `intent_router`).
- **Deterministic Mocking:** Supply consistent inputs and outputs for `MockLLM` so the entire Abhyas platform can run end-to-end locally and in CI without external API keys.
- **Negative Rejection:** `fail_*.json` fixtures verify that malformed, hallucinated, or ungrounded outputs are strictly rejected by role guards.
