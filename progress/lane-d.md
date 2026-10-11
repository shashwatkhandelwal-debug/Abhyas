# Lane D Progress (Content, Evaluation & Documentation)

Branch: `lane-d`
Worktree: `../abhyas-d`
Port: 8004
Database: Mock/offline (no DB required)

## Tasks
- [x] T37 Demo data & worked example script (user testing kit, Ravi script, eval samples)
- [ ] T38 Golden fixtures (>=5 per runtime role)
- [ ] T39 Evaluator samples audio render
- [ ] T40 Source ingestion & chunking
- [ ] T41 Latency benchmark
- [ ] T42 Kappa harness
- [ ] T43 Guard report
- [ ] T44 Realism report & blind pairs
- [ ] T45 Content pipeline (generate/review/publish)

## Deliverables in T37
- `eval/user_testing/consent_form_hi.md`: Plain everyday Hindi consent form for primary teachers (<250 words, unselected checkboxes, spoken script, contact line).
- `eval/user_testing/exit_questions_hi.md`: Post-session survey in Hindi (realism 1-5, usefulness 1-5, weekly use, hardest step, 5-item SUS-lite).
- `eval/user_testing/observer_guide.md`: Step-by-step 30-40 min protocol for field lead (Divyansh) covering think-aloud observation and zero-PII logging.
- `eval/user_testing/sessions.csv`: Anonymised session schema (header only, zero invented rows).
- `eval/user_testing/round1_findings.md`: Round 1 empty findings template with headings, tables, and placeholders only.
- `eval/user_testing/round2_findings.md`: Round 2 empty findings template with headings, comparison table, and placeholders only.
- `docs/worked_example_ravi.md`: Complete pedagogical and technical script for Ravi worked example (52-17 and 43-27), tagged acts, rule engine transitions, allowed/forbidden sets, child voice output, and relapse test.
- `eval/samples/samples.yaml`: Evaluator sample inputs per spec/10 §10.1 and spec/13 §13.1.
- `content/tests/test_user_testing_and_samples.py`: 7 automated validation tests for kit artifacts, samples, and CI guard against premature data.

## Deviations from spec
None. All artifacts conform strictly to spec/10, spec/11, and spec/14.

## Self-Reviews
- T37 Self-Review: Verified against spec/11 §11.6, spec/10 §10.3, and spec/04 §4.5. All files NFC normalized, zero PII, 16/16 content tests passing cleanly, ruff check and ruff format clean.

