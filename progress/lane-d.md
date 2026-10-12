# Lane D Progress (Content, Evaluation & Documentation)

Branch: `lane-d`
Worktree: `../abhyas-d`
Port: 8004
Database: Mock/offline (no DB required)

## Tasks
- [x] T37 Demo data & worked example script (user testing kit, Ravi script, eval samples)
- [x] T38 Golden fixtures (>=5 per runtime role)
- [x] T39 Evaluator samples audio render
- [ ] T40 Source ingestion & chunking
- [ ] T41 Latency benchmark
- [ ] T42 Kappa harness
- [ ] T43 Guard report
- [ ] T44 Realism report & blind pairs
- [ ] T45 Content pipeline (generate/review/publish)

## Deliverables in T39
- `scripts/render_samples.py`: Rendering pipeline for `eval/samples/samples.yaml` supporting Sarvam TTS (adult voice), human pre-recordings (`eval/samples/recorded/`), and synthetic speech placeholder fallback, with CLI options (`--mock`, `--force`).
- `eval/samples/audio/`: Rendered audio files for all 5 evaluator samples in both `.wav` and `.ogg` formats (`s1` through `s5`).
- `eval/samples/demo_chips.json`: Structured manifest of demo chips with step, Devanagari chip labels, NFC-normalized prompts, audio references, and expected behaviors.
- `README.md`: Added Section 3 Evaluator Sample Inputs table per spec/13 §13.1.
- `content/tests/test_render_samples.py`: 5 automated tests for sample YAML loading, synthetic WAV validity, mock rendering, human recorded override, and CLI execution.
- `content/tests/conftest.py`: Pytest configuration for clean path resolution.


## Deliverables in T38
- `backend/tests/golden/act_tagger/`: Golden fixtures covering teacher pedagogical acts and bad variants with invalid quotes.
- `backend/tests/golden/child_voice/`: 5 golden fixtures across Ravi, Priya, Aman with persona voice, allowed numbers, and bad variants leaking forbidden numbers or unauthorized digits.
- `backend/tests/golden/coach/`: 5 golden fixtures across exemplar and developmental teaching turns with verbatim evidence quotes and bad variants with hallucinated quotes.
- `backend/tests/golden/fidelity_checker/`: 5 golden fixtures for checklist verification against transcripts and bad variants.
- `backend/tests/golden/intent_router/`: 5 golden fixtures for intent classification across states and bad variants with invalid intents.
- `backend/tests/golden/question_classifier/`: 5 golden fixtures for classifying teacher questions into pedagogy/classroom/admin/out-of-scope and bad variants.
- `backend/tests/golden/guide_answerer/`: 5 golden fixtures grounded in retrieved chunks with citations and bad variants with ungrounded answers.
- `backend/tests/unit/test_golden_fixtures.py`: Automated tests asserting schema validation, NFC normalization, guard verification, and bad variant rejection across all 7 runtime roles.

## Deliverables in T37
- `eval/user_testing/consent_form_hi.md`: Plain everyday Hindi consent form for primary teachers (<250 words, unselected checkboxes, spoken script, contact line).
- `eval/user_testing/exit_questions_hi.md`: Post-session survey in Hindi (realism 1-5, usefulness 1-5, weekly use, hardest step, 5-item SUS-lite).
- `eval/user_testing/observer_guide.md`: Step-by-step 30-40 min protocol for field lead (Divyansh) covering think-aloud observation and zero-PII logging.
- `eval/user_testing/sessions.csv`: Anonymised session schema (header only, zero invented rows).
- `eval/user_testing/round1_findings.md`: Round 1 empty findings template with headings, tables, and placeholders only.
- `eval/user_testing/round2_findings.md`: Round 2 empty findings template with headings, comparison table, and placeholders only.
- `docs/worked_example_ravi.md`: Complete pedagogical and technical script for Ravi worked example (52-17 and 43-27), tagged acts, rule engine transitions, allowed/forbidden sets, child voice output, and relapse test.
- `eval/samples/samples.yaml`: Evaluator sample inputs per spec/10 §10.1 and spec/13 §13.1.
- content/tests/test_user_testing_and_samples.py: 7 automated validation tests for kit artifacts, samples, and CI guard against premature data.

## Deviations from spec
None. All artifacts conform strictly to spec/05 §5.11, spec/10, spec/11, and spec/14.

## Self-Reviews
- T39 Self-Review: Implemented `scripts/render_samples.py` to synthesize evaluator sample inputs into `eval/samples/audio/` (.wav & .ogg) via Sarvam TTS / recordings / synthetic audio with duration proportional to text. Generated `eval/samples/demo_chips.json` manifest with Devanagari chip labels. Updated `README.md` per spec/13 §13.1. All 21 content tests pass cleanly; ruff and mypy pass.
- T38 Self-Review: Validated all 7 runtime LLM roles have >= 5 golden fixtures in `backend/tests/golden/<role>/`. Each fixture checked against Pydantic output schemas, NFC normalization, and runtime guards. Bad variants verified to fail either schema validation or guard criteria. All tests pass cleanly (15/15).
- T37 Self-Review: Verified against spec/11 §11.6, spec/10 §10.3, and spec/04 §4.5. All files NFC normalized, zero PII, 16/16 content tests passing cleanly, ruff check and ruff format clean.


