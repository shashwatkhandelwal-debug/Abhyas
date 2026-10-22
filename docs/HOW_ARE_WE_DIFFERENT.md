# Abhyas versus "a general chatbot given the same two PDFs"

Only differences that exist in the code are listed. Each row names the file or test that shows it. (We use more
than two documents: five are ingested, see `content/chunks/`.)

| | A general chatbot with the PDFs | Abhyas | Where to look |
|---|---|---|---|
| **Who decides what the child answers** | The model, so the child's mistake drifts and the child "learns" from being told. | A deterministic rule engine decides the answer, the mistake and whether the child improves; the model only words the line. | `backend/app/rule_engine/engine.py`; tests `test_spec_4_5_2_ravi_worked_example`, `test_spec_4_5_3_relapse_after_tell`, `test_spec_4_5_10_determinism` (`backend/tests/unit/test_rule_engine.py`) |
| **Checking the model's words** | Whatever it says is shown. | Each model line is checked: only the engine's numbers, no forbidden number, no placeholder, no digression, word cap; one retry, then a fixed template. Coach quotes must appear in the teacher's own words. | `backend/app/llm/guards.py` (`guard_child_line`, `guard_coach`, `guard_act_tagger`); `backend/tests/unit/test_guards.py`, `test_child_voice.py` |
| **When the model is down** | An error or an empty reply. | Every role has a deterministic fallback; failures are logged with `fallback_used`; a daily token budget degrades to fallbacks instead of failing. | `backend/app/llm/client.py` (`TokenBudgetTracker`), `llm/roles/*.py`; `test_llm_role_robustness.py` |
| **Same input, same child** | No: the child varies from run to run. | Yes for the answer, state and kind; only the wording can vary. | `test_spec_4_5_10_determinism`; `docs/SAMPLE_INPUTS.md` |
| **Citations** | Plain text, page numbers often invented. | Answers carry the source and page of the passages actually used; a tap opens the excerpt (`/api/source/<chunk_id>`); the guard requires cited sources to be among the retrieved ones and numbers to come from them. | `backend/app/llm/roles/guide_answerer.py`, `guard_guide_answerer`; `backend/app/web/chat_api.py` (`get_source_excerpt`); `test_guard_guide_answerer_fail_number_in_uncited_chunk_only` |
| **Off-topic and unsupported questions** | Answers anything. | Off-topic questions are declined; a question the documents do not support gets "not in my documents" or goes to the ARP. Rates are measured in `docs/PERFORMANCE.md`. | `RETRIEVAL_MIN_SCORE`, `RETRIEVAL_MIN_MATCHED_TERMS` in `config.py`; `backend/app/retrieval/search.py`; `eval/retrieval_recall.py` |
| **The diagnosis verdict** | Would judge the teacher's diagnosis in free text, differently each time. | "What is this child's mistake?" is compared with the child's real mistake by fixed keyword rules (correct / partly / wrong); the model is consulted only for text matching nothing, and it can only name a candidate that the rules then verify. | `backend/app/rehearsal/diagnosis.py`; `test_classifier_id_names_a_candidate_but_the_matcher_decides` (`backend/tests/unit/test_one_on_one.py`) |
| **A weekly loop with an evidence ladder** | A conversation with no structure. | Learn, explain back, model, rehearse, feedback, retry, try in class, reflect; adoption evidence is recorded on a five-level ladder and an ARP can add an observation. | `backend/app/sessions/state_machine.py`; `AdoptionEvidence` in `backend/app/db/models.py`; `/arp` observation form |
| **Per-role consent and suppression** | No notion of roles. | A teacher's scores reach the ARP only with consent; the trainer sees counts only and nothing for groups under 10; no names. | `config.py` `AGGREGATION_SUPPRESSION_N`; `test_non_consenting_teacher_never_appears_by_name_or_score`, `test_trainer_suppression_n_less_than_10`, `test_trainer_dashboard_suppression_and_no_teacher_pii` |
| **Reset of shared demo logins** | n/a | Logging out of a shared demo teacher restores the seeded state; the admin "Reset demo" uses the same code path. | `backend/app/db/seed.py` (`reset_demo_teacher`); `backend/tests/integration/test_demo_reset_postgres.py` |
| **Low connectivity** | Needs a live connection and a heavy page. | Light server-rendered pages (under 150 KB), a service worker, an IndexedDB outbox that retries with backoff, lite mode, offline checklist, a "server waking up" page and bilingual error pages. | `backend/app/web/static/sw.js`, `chat.js`; `backend/tests/js/*.test.mjs`; `backend/tests/unit/test_check_first_load.py`; `backend/tests/unit/test_error_pages.py` |
| **Human in the loop** | None. | Low-confidence scores and escalated questions go to a review queue where a coach resolves them or labels scenes for calibration. | `backend/app/web/review.py`, `ReviewItem`, `CalibrationLabel` |

## What we do not claim

- We have not measured that Abhyas teaches better than a chatbot. The differences above are about control,
  repeatability and auditability, which we can show; learning outcomes we cannot yet show.
- A good chatbot with the same PDFs can answer "how do I teach X?" well; the retrieval and citation layer here is
  there to make that answer checkable, not to out-write it.
- The kappa agreement with human coaches and the realism rating by teachers were not measured
  (`docs/QA_SHEET.md` questions 6 and 10).
