# The 15 hardest questions, with honest answers

Every answer points to a file, a test or a number in this repository. A claim that cannot be checked from the
repository is marked **[UNVERIFIED]**. Numbers from our own runs are in `docs/PERFORMANCE.md` (with date and git
SHA) and in `eval/`.

**1. Why not just a chatbot with these PDFs?**
A chatbot would play the child, so the child's mistakes would drift, the child would "learn" from being told, and
none of it could be replayed or tested. Here the child's answer, mistake and progress come from a deterministic
rule engine (`backend/app/rule_engine/`); the model only voices a line that must contain the engine's numbers
(`guard_child_line` in `backend/app/llm/guards.py`). The PDFs do a separate job: answering "how do I teach X?"
with page citations (`backend/app/retrieval/`, role `guide_answerer`). See `docs/HOW_ARE_WE_DIFFERENT.md`.

**2. How do you stop the model deciding what a child answers?**
By construction and by test. `RuleEngine.step` (`rule_engine/engine.py`) returns a `ChildResponse` with `kind`,
`answer`, `allowed_numbers` and `forbidden`; `child_voice` receives only that. `guard_child_line` rejects a line
with a number outside `allowed_numbers`, a forbidden number, a missing answer on an answer-kind, a digression, an
out-of-character word or a leaked placeholder; one retry, then a fixed template (`llm/roles/child_voice.py`;
tests in `test_child_voice.py`, `test_guards.py`). The engine is tested for determinism and for the Ravi example
(`test_spec_4_5_2_ravi_worked_example`, `test_spec_4_5_10_determinism` in `test_rule_engine.py`). The model also
tags what the *teacher* did (`act_tagger`), but that only selects which engine rule applies, and a quote the tagger
cites must appear in the teacher's words (`guard_act_tagger`). Residual risk: a mis-tagged act changes which rule
fires. We measured tagger fallbacks (0 of 41 in `eval/one_on_one/LIVE_REPORT.md`), not tagger accuracy against
coaches **[UNVERIFIED]**.

**3. What happens when the model is down or slow?**
Every role has a deterministic fallback after one retry: child lines use `template_line`, the coach uses
`fallback_coach_feedback`, explain-back uses `fallback_fidelity`, diagnosis falls back to keywords, the module
check to keyword match, and a question to "not in my documents" or escalation to the ARP. A daily token budget
(`LLM_DAILY_TOKEN_BUDGET`, `TokenBudgetTracker` in `llm/client.py`) raises `TokenBudgetExceeded`, a kind of
`LLMUnavailable`, so the same fallbacks run instead of an error. Tests: `test_llm_role_robustness.py`,
`test_child_voice.py::test_voice_child_line_fallback_on_double_failure`. Every role call is logged
(`llm_role role=… fallback_used=…`) and `eval/measure_latency.py` reports the fallback share. The teacher never
sees a stack trace (`backend/app/web/errors.py`, `test_error_pages.py`). The fallback text is plainer, not wrong.

**4. What about bias and safety?**
The children are synthetic; no real child's data is used. Their register is constrained by guards (word cap, no
out-of-character terms, no digressions unless the engine chose one). The coach must quote the teacher's own words
and may not address the teacher disrespectfully (`guard_coach`; tests `test_guard_coach_fail_*`). Questions
outside teaching are declined (`out_of_scope`, message `ask_out_of_scope`); admin questions go to a human. What we
have **not** done: a bias audit of the Hindi output across dialects, or of the speech recogniser on rural accents
**[UNVERIFIED]**; and there is no separate content-moderation model on teacher input. The misconception library
is reviewed only by us so far (see question 11).

**5. Privacy and consent?**
Private by default: `consent_share_scores` is false unless the teacher agrees. The ARP digest lists only
consenting teachers (`test_non_consenting_teacher_never_appears_by_name_or_score`,
`test_arp_access_in_own_cluster_consenting_vs_non_consenting`). Trainer views hide any group under
`AGGREGATION_SUPPRESSION_N` = 10 (`config.py`; `test_trainer_suppression_n_less_than_10`,
`test_trainer_dashboard_suppression_and_no_teacher_pii`) and show no names. Phone numbers are stored as salted
hashes, with the reversible form Fernet-encrypted in a separate table (`privacy/hashing.py`). A teacher's voice
note is read into memory, transcribed and dropped (`channels/web.py`; the only `audio_ref` column holds the cache
key of *synthesized* replies). A teacher can delete their data (`/teacher/delete`, `privacy/purge.py`). Consent
changes are logged (`ConsentLog`). The synthetic cohort and shared demo logins are labelled demo. A legal review
of the data-protection position was not done **[UNVERIFIED]**.

**6. How is it evaluated?**
Four kinds of evidence exist. (a) Automated tests (backend pytest suite plus Node tests for the PWA; `make test`).
(b) Real-model runs: ten scripted one-on-one scenes (`eval/one_on_one/LIVE_REPORT.md`: 0 fallbacks in 41
act-tagger, 41 child-voice and 10 coach calls, 0 word-cap violations) and retrieval recall
(`eval/retrieval_recall.py`; numbers in `docs/PERFORMANCE.md`). (c) Latency by stage from the role logs
(`docs/PERFORMANCE.md`). (d) Memory (`docs/PERFORMANCE.md`). **Not done:** the kappa study of the AI coach against
two human coaches (harness in `eval/calibration/`, but the double coding by coaches did not happen: see
`PROGRESS.md › Blocked on humans`), the realism survey with teachers, and the user-testing rounds
(`eval/user_testing/` holds blank templates). So we have no measured agreement with experts and no measured
teacher outcome **[UNVERIFIED]**.

**7. What does it cost per teacher?**
In the ten-scene live run the LLM spend was about US$0.125 for 10 scenes (`eval/one_on_one/LIVE_REPORT.md`),
roughly US$0.0125 per rehearsal scene including act tagging, child lines and coach feedback; the latest
measurement is in `docs/PERFORMANCE.md`. Speech cost is not included (speech is mock here; prices are in
`config.py` and `eval/cost/cost_report.py`). A per-teacher-per-year figure needs real usage and speech spend,
which we do not have: **[UNVERIFIED]**. A weekly loop is about one scene plus an explain-back check and a few
questions, so the LLM share is probably small, but that is an estimate, not a measurement.

**8. Does it scale?**
Not as built, and we say so. The evaluation deployment is one process on Render's free plan: the conversation
lock and the scheduler live in the process (`docs/DEPLOY.md`: one worker, one instance), and the retrieval index
is held in memory (`retrieval/search.py`; memory in `docs/PERFORMANCE.md`). Scene state can live in memory or in
Postgres (`rehearsal/scene_store.py`). Scaling out would need a shared lock and a job queue; most state is already
in Postgres so the change is bounded, but it is not built or tested **[UNVERIFIED]**. We have not load-tested more
than a handful of concurrent users; `eval/latency/REPORT.md` is a mock-provider run.

**9. What is real and what is simulated?**
Real: the engine, guards, fallbacks, Claude calls, retrieval over five ingested documents with page citations,
consent and suppression, the outbox and PWA. Simulated: the children; the ARP/trainer data (51 fictional teachers,
scores from the real engine on scripted turns, `db/demo_data.py`, labelled demo); speech is mock unless provider
keys are set; WhatsApp works only with Meta credentials. The two Hindi UP guides were machine-read from page
images and not yet human-checked (`docs/EVALUATOR_GUIDE.md`, `docs/ocr_samples/`). No real teacher has used the
system **[UNVERIFIED: there is no field-trial data in the repository]**.

**10. What would you do with more time?**
In order: (1) a coach double-coding session to get the kappa number and fix the rubrics; (2) a field trial with
real teachers on WhatsApp and voice, measuring completion and adoption evidence; (3) have an FLN coach approve
the move cards (all four are `status: in_review` in `content/moves/`) and the diagnosis keyword sets; (4) more
moves and a literacy one-on-one; (5) a shared lock and a job queue for scale; (6) a speech-accuracy test on rural
Hindi accents (`eval/stt/` is a harness, not a result).

**11. How does an FLN coach review the content?**
Through `/review` (login `coach.demo`): a queue of AI scores that need a human look (`ReviewItem`,
`backend/app/web/review.py`), a calibration view where a coach labels a scene so agreement can be computed
(`CalibrationLabel`, `eval/calibration/kappa.py`), and a move-card review page (`review_move.html`) for editing
and approving a card. Content has a status field; all four shipped cards are still `in_review`
(`content/moves/*.yaml`), so **no card has been approved by a human yet**. The review tooling exists; the coaches'
review has not happened.

**12. Why a rule engine, not a prompted or fine-tuned model, for the children?**
Because the promise is that practice is repeatable and fair: the same teacher action gets the same child
behaviour, so progress and feedback mean something and a coach can audit a transcript. A model playing the child
cannot give that. The price is coverage: the engine models three numeracy moves and one literacy move with a fixed
set of misconceptions (`rule_engine/bugs/`, `content/personas/`); anything else gets a `confused` reply or no
change of state (`test_spec_4_5_5_ineffective_acts_never_advance`).

**13. How do you know the answers to teachers' questions are grounded?**
`guard_guide_answerer` requires cited sources to be a subset of the retrieved chunks and numbers to come from the
cited chunks (`test_guard_guide_answerer_fail_number_in_uncited_chunk_only`); a retrieval gate
(`RETRIEVAL_MIN_SCORE`, `RETRIEVAL_MIN_MATCHED_TERMS` in `config.py`) refuses to answer without support and the
reply says "not in my documents". Off-topic rejection and recall@5 are re-measured in `docs/PERFORMANCE.md`. The
Class 1 maths guide has no page on two-digit subtraction with regrouping, so the demo move is not backed by an
official page and the system says so rather than invent one (`docs/EVALUATOR_GUIDE.md`). Whether the *pedagogy* in
an answer is right was not checked by a subject expert **[UNVERIFIED]**.

**14. What does a teacher do in a week, and how would you know practice changed?**
A loop: learn, explain back, model, rehearse, feedback, retry, try in class, reflect (`sessions/state_machine.py`,
`docs/worked_example_ravi.md`). Evidence of adoption is a five-level ladder (`AdoptionEvidence.level` is 1–5),
including an ARP observation form on `/arp`. The ladder and the form exist; we have no data on whether practice
changed in a real classroom **[UNVERIFIED]**.

**15. What breaks first in the one hour we have?**
Likeliest: the cold start (about a minute on the free plan; the pages say so and open by themselves); a missing
or slow voice provider (the chat tells the teacher to type instead); other judges using the same shared demo
teacher at the same moment (they reset on logout, so stay in your own session). Known weaknesses: the act tagger
can mis-tag an unusual Hindi/Hinglish sentence, and the child's wording varies between runs (its numbers do not).
See `docs/JUDGE_QUICKSTART.md`.
