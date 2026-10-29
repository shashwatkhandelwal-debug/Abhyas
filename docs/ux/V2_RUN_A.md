# V2 run A report

## Done
- Branch feat/v2-national created from main (62014e5); tag pre-v2-build created.
- A1: docs/ux/V2_DESIGN.md. Written from reading code. alembic head verified by running `alembic heads` (c4e6a8b0d2f3). Everything else is from reading, not running. I did not read render.yaml, so "production sets DEMO_MODE=false" is assumed.
- A2: address form.
  - Stored as teacher.address_form ('f'/'m') at onboarding PROFILE_ADDRESS; passed via SessionContext into get_message (text_m) and into child_voice (template_line and the LLM prompt's {teacher_address}), scripted off-topic lines (replace दीदी/मैडम -> सर) and prewarm audio variants (prewarm_lines.py already renders both). That already worked; no guard allowed-word list blocks "सर" (no data change needed there).
  - Changes: content/messages_hi.yaml (text_m for consent_details "चुनते हैं", hint_model "दूसरे शिक्षक ... करते हैं"); backend/app/llm/roles/act_tagger.py keyword fallback regex now `दिखात[ाी]` / `बतात[ाी]` (a regex data tweak, not the rule engine or guards).
  - Not changed (recorded): speaker_model_teacher "आदर्श शिक्षिका" (label of the model teacher, third party, exempted by an existing content test); ui_offline_chk4_text and UI placeholders (static pages, not address-aware); act_examples_hi.yaml feminine few-shot examples (LLM prompt only, not shown to teachers; the fallback tagger now handles both genders).
  - Real SessionService path, mock tagger, no LLM. Child lines seen (tests print them):
    - one-on-one (out-of-range problem), she: "दीदी, ये तो बहुत बड़ा है… समझ नहीं आया।"; he: "सर, ये तो बहुत बड़ा है… समझ नहीं आया।"
    - group (literacy), she: "दीदी, आज मिड-डे मील में क्या है?"; he: "सर, आज मिड-डे मील में क्या है?" (other group lines "मे - ला!" carry no address).
    - Ordinary one-on-one answers ("24!") have no address; the engine never substitutes off-topic for an answer.
  - Tests: backend/tests/unit/test_teacher_address.py (12 tests, f and m, Hindi and English): pass.

## Verified (run this session)
- ruff check . clean; mypy --strict backend/app scripts/keep_alive.py clean (before the final A1 commit, no Python changed after).
- check_first_load.py before and after: unchanged (127.63 / 148.28 KB).
- Targeted tests (test_teacher_address, act_tagger, conversation, messages_en, child_voice, content/tests) pass.
- Full run via scripts/pytest_fresh_db.py --server postgresql://postgres:postgres@127.0.0.1:5433/postgres: **3 failed, 1620 passed, 2 skipped, 127 errors in 1045.57s**. Cause: `extension "vector" is not available` (66 occurrences) on that server; the failing tests are DB ones (migrations round trip, seed on fresh postgres, integration/e2e needing the schema). Docker Desktop is not running, so the project's pgvector container could not be started. I did not rerun (the cause is the environment, not a commit; there was nothing to revert). Gate is therefore NOT green; needs a pgvector Postgres. Whether the same failures occur on main is assumed, not tested. Raw output: docs/ux/_v2a_full_gate.txt.
- node chat tests and composer_layout_check not run: no client or layout file changed.

## Not done / assumed
- Full gate green: not achieved (above).
- Nothing pushed-to-main, merged or deployed. No Anthropic API calls.

## Update: full gate rerun with the project's pgvector database
- No earlier test run was left using the database (I stopped my unfinished unit-test run, PID 5132; no python processes remained; 0 `abhyas_test*` connections).
- DB: the repo's docker compose service `abhyas-db-1` (pgvector/pgvector:pg16, port 5432) was already up. `CREATE EXTENSION IF NOT EXISTS vector` succeeded (already present, version 0.8.7).
- Command: `python scripts/pytest_fresh_db.py --server postgresql://postgres:postgres@127.0.0.1:5432/postgres` (no -q), run once.
- Summary line: **1751 passed, 1 skipped in 713.52s (0:11:53)**. The one skip is test_evaluator_samples (no audio files on disk, HUMAN INPUT). Raw output: docs/ux/_v2a_full_gate_rerun.txt.
- So the earlier failures (3 failed, 127 errors) were the missing pgvector extension on the :5433 server, not the commits. The worktree comparison against main was not needed (no failures). The gate is green; this supersedes the "NOT PASSED" lines above.

## git show --stat for the three commits
```
c869d94 V2-A2: teacher form of address follows onboarding choice (consent/hint text_m, he/she model-step tagger, tests)
 backend/app/llm/roles/act_tagger.py        |   2 +-
 backend/tests/unit/test_teacher_address.py | 126 +++++++++++++++++++++++++++++
 content/messages_hi.yaml                   |   3 +-
 3 files changed, 129 insertions(+), 2 deletions(-)

2c86716 V2-A1: v2 design note (hooks for check-in, child strip, level sorter, talk-move feedback, labels, cluster pack)
 docs/ux/V2_DESIGN.md | 82 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 82 insertions(+)

41fad82 V2 run A: progress and run report
 docs/ux/V2_PROGRESS.md     |     9 +
 docs/ux/V2_RUN_A.md        |    25 +
 docs/ux/_v2a_full_gate.txt | 27800 +++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 27834 insertions(+)
```
