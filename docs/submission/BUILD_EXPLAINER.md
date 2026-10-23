# Build explainer: how Abhyas works, for the person who has to explain it live

**Who this is for.** One teammate, not a programmer, who may be asked to explain the build in front of the judges.
Every claim below points to a file, a test or a measured number in this repository. When something cannot be
checked from the repository it is marked **[UNVERIFIED]**: say so out loud if you are asked about it. Do not
promise anything that is marked that way.

**How to use it.** Read "The one-minute story", then one page per layer (each has what to say in 60 seconds, the
files, and what to show). Practise the three "show me" paths on the hosted demo accounts. The 5-minute walkthrough
and the 20 hard questions are at the end.

Open the repository on GitHub in a browser tab before you start: when someone asks "where is that?", you open the
file named here. You do not need to read code; the file names and the short descriptions are enough.

---

## The one-minute story

Government teachers in Classes 1 to 3 are trained in teaching moves but almost never get to practise them, and
trainers see attendance, not what changed in class. **Abhyas** lets a teacher practise one move for about fifteen
minutes a week, by voice, in Hindi, with a simulated child.

The idea that makes it different: **a computer program with fixed rules, not an AI model, decides what the child
answers.** Ravi really does subtract the smaller digit from the larger one (43 − 27 = 24); if the teacher just tells
him the right answer he repeats it like a parrot and makes the same mistake on the next problem, as real children
do. The AI model only does the things language models are good at, under guard: it works out which teaching move
the teacher used, puts the child's answer into a natural Hindi sentence, writes the coach's feedback quoting the
teacher's own words, and answers how-to questions **only** from official documents, with the page number.

Everything the AI produces is checked by code before a teacher sees it; if a check fails twice, a fixed template
is used instead. Everything the teacher picks from a list (a class struggle, a skill to improve) is a closed list,
so nothing can be invented.

**Honest status.** The build is complete as a demo. No real teacher has used it, no coach has measured how well
the AI coach agrees with human coaches, and the speed on the hosted free plan has not been measured. Those are in
the roadmap, not claimed.

### How the product was built (say this plainly)

The code was written by an **AI coding assistant (Claude Code) working from specifications written by the team**
(the `spec/` folder and `AGENTS.md`). The team did not hand-write the code. Each change was **reviewed by a separate
reviewer** before it was kept (the team's process; the review findings and fixes are recorded in `PROGRESS.md`,
and the commit messages are numbered per task). The work is held in place by **automated gates run after every
change**: a style check (`ruff`), a type check (`mypy --strict`), and a test suite of about 1,500 tests
(`pytest`, plus Node tests for the web chat). The exact total at the end of this build is in
`PROGRESS.md` under "Gate totals". If asked "did you write this?": "We wrote the specification and made every design
decision; an AI assistant wrote the code from it, a separate reviewer checked every change, and the test suite is
what we trust." That is true and it is the answer.

---

## Layer 1: Data input (what goes in)

**Say in 60 seconds.** Three kinds of things go in. First, what the teacher says or types: a voice note on the web
chat or WhatsApp, a typed message, or a tap on a button. A speech service turns the voice into Hindi text and the
audio is dropped, not stored. Second, the teaching content: four move cards written by us (each describes a
teaching move, the children's misconceptions, a scoring rubric and feedback lines), and five official documents we
ingested (NIPUN Bharat guidelines, NCERT Vidya Pravesh, NISHTHA FLN, and two Uttar Pradesh teacher guides in Hindi),
cut into 1,157 searchable passages that each remember their page. Third, small closed lists we wrote: 14 class
struggles, 10 handbook starter questions, 5 teaching skills. Nothing else goes in; there is no real teacher or child
data in the repository.

| What | Where (open this file) | Notes |
|---|---|---|
| Web chat page and API | `backend/app/web/teacher.py`, `backend/app/web/chat_api.py`, `backend/app/web/static/chat.js` | Plain HTML and JavaScript, no framework; the page stays light for cheap phones |
| WhatsApp channel | `backend/app/whatsapp/`, `backend/app/channels/` | Built; **works only with Meta credentials**, which we do not have in the repo [UNVERIFIED against live Meta] |
| Speech to text | `backend/app/speech/stt.py`, `speech/audio.py` | Providers: Sarvam, Gemini, Bhashini, mock. A rate-limited provider is skipped and the next one is used |
| Move cards | `content/moves/*.yaml` (4 files) | All four are marked `in_review`: **no coach has approved them yet** |
| Official documents, cut into passages | `content/chunks/*.jsonl`, `content/sources/sources.yaml`, `backend/app/retrieval/source_chunks.py` | 1,157 passages. Two Hindi guides were read from page images by an AI step and are marked machine-read in citations |
| Closed lists | `content/class_struggles.yaml`, `content/handbook_questions.yaml`, `content/teaching_skills.yaml` | Every item is tied to a real passage and checked by a test |
| All Hindi and English wording | `content/messages_hi.yaml`, `content/messages_en.yaml` | One catalogue; a test keeps the two languages in step |
| Fictional cohort for the trainer and ARP pages | `backend/app/db/demo_data.py` | 51 fictional teachers, labelled demo |

**Show me: a cited handbook question.** Log in as `teacher.demo1`. Under the text box tap one of the four
"हैंडबुक से पूछें" chips. The answer appears with "स्रोत: ..., पृष्ठ N". Tap the source chip: the exact passage
opens. Say: "The answer can only come from these passages; if nothing matches, it says so."

---

## Layer 2: Processing (what the program does with it)

**Say in 60 seconds.** A weekly loop with fixed steps: learn the move, explain it back, hear a model teacher, rehearse
with a child, get feedback, retry, plan to try it in class, reflect. A **state machine** keeps track of where the
teacher is. During the rehearsal, each teacher sentence goes through five stages: (1) speech to text; (2) a small
AI model labels which teaching move the sentence was (for example "asked the child to explain"); (3) the **rule
engine**, plain code with no AI, decides what the child does next from those labels: which answer, which feeling,
whether the misconception melts or comes back; (4) a small AI model turns the engine's decision into one natural
Hindi sentence, and a guard rejects the sentence if it contains any number the engine did not choose; (5) text to
speech, and everything is saved. A bigger AI model writes the coach feedback at the end. Questions to the app go to
a search over the official passages first, then an AI model writes a short answer using only what was found.

| What | Where | Notes |
|---|---|---|
| The weekly loop | `backend/app/sessions/state_machine.py`, `sessions/service.py` | The state machine is the product's spine; the service wires it to the database |
| The scene (5 stages) | `backend/app/rehearsal/scene_runner.py` | Timing of each stage is logged |
| **The rule engine (the core idea)** | `backend/app/rule_engine/engine.py`, `child_state.py`, `transitions.py`, `misconceptions.py`, `bugs/` | About 1,900 lines of ordinary code (with the bug library). It imports no AI library; a test checks that it does not know about skills, the class profile or any model |
| The AI roles (13 of them) | `backend/app/llm/roles/` | `act_tagger`, `child_voice`, `coach`, `diagnosis_classifier`, `guide_answerer`, `question_classifier`, `class_struggle_classifier`, `teaching_skill_classifier`, `coach_suggestion`, `module_check`, `fidelity_checker`, `intent_router`, `translator`. Each has its own prompt in `llm/prompts/` |
| Search over the documents | `backend/app/retrieval/search.py` | Word-matching (BM25), no AI at search time, in Hindi |
| My class, skills, path order | `backend/app/class_profile/` | Closed lists; the path puts the moves that practise her class's struggle first |
| Scores to the trainer | `backend/app/reports/` | Counts only, with small-group suppression |

**Show me: a teacher scene.** Log in as `teacher.demo2` (already in a one-on-one scene with Ravi, problem 43 − 27).
Tap a sample chip, or speak "रवि, तुमने 43 में से 27 कैसे घटाया? एक-एक कदम बताओ।". Ravi explains his own mistake and
answers 24. Now send "रवि, सही उत्तर 16 है, इसे याद कर लो।": he repeats 16. Send "अब नया सवाल: 61 में से 28।": he answers 47,
the same mistake again. Say: "The AI did not decide that. The rule engine did, and it will do exactly the same every time."
Outputs of this exact run are in `docs/SAMPLE_INPUTS.md` (inputs 2 and 4).

---

## Layer 3: Guardrails (what stops it going wrong)

**Say in 60 seconds.** Seven layers. One: the child's answer comes only from the rule engine, so the AI cannot make
a child say the wrong thing. Two: every AI output must fit a fixed structure (a "schema"), or it is rejected. Three:
each role has a guard in code: the child's line may contain only the numbers the engine chose and no more than
25 words and may not mention "AI" or "misconception"; the coach must quote the teacher's own words and may not talk
down to the teacher; an answer to a question must cite a passage that was actually retrieved. Four: on a failed
guard the call is tried once more, then a fixed template is used, and the failure is logged. Five: closed lists, so a
teacher's words can only become an item from a list we wrote. Six: privacy and consent: scores are private until the
teacher agrees to share, the trainer sees only groups of ten or more, deletion on request. Seven: operational: a login
limiter, spending caps on AI and speech, and no secrets in the repository (a scanner checks).

| What | Where | Notes |
|---|---|---|
| The guards, role by role | `backend/app/llm/guards.py` | One function per role |
| Structure checks | `backend/app/llm/schemas.py`, `llm/client.py` | Forced tool call, schema-validated |
| Fallbacks | each file in `llm/roles/` | Template child line, template coach feedback, keyword diagnosis, "not in my documents" |
| Guard failures logged and counted | `backend/app/llm/guard_stats.py`; report: `eval/guards/REPORT.md` | **No live traffic data yet**; the report shows the adversarial test corpus: 8 of 8 unsafe lines blocked |
| Tell-the-answer relapse | test `test_spec_4_5_3_relapse_after_tell` in `backend/tests/unit/test_rule_engine.py` | The central claim, enforced by a test |
| "No model changes a child's answer" | `backend/tests/unit/test_teaching_skills.py`, `test_class_profile_personalise.py` | A hostile model output and a class profile do not change a single answer |
| Consent and small groups | `backend/app/reports/`, `backend/app/privacy/purge.py`, `AGGREGATION_SUPPRESSION_N = 10` in `backend/app/config.py` | Tests named in `docs/QA_SHEET.md` question 5 |
| Handbook answers cite or decline | `backend/app/llm/roles/guide_answerer.py`, `handbook/fallback.py` | Off-topic questions: 20 of 20 not answered with real models (`docs/PERFORMANCE.md` section 3) |
| Spending caps, login limits, CSRF | `backend/app/speech/spend.py`, `llm/client.py` (token budget), `auth/rate_limit.py`, `auth/csrf.py` | |
| Secret scan | `scripts/freeze_check.py` and CI | |

**Show me: the diagnosis verdict.** Log in as `teacher.demo2`. End the scene (the end-practice button), choose retry,
choose "1-1 बच्चे से बात" and Ravi, then say "रवि बड़ी संख्या में से छोटी घटा देता है, उल्टा कर देता है". The app compares
your sentence with Ravi's real mistake and says correct, partly or wrong, then reveals the mistake. Pick Priya instead
and say the same sentence: the verdict is **wrong**, because her mistake is different. Say: "The verdict is decided by
fixed keyword rules (`backend/app/rehearsal/diagnosis.py`); the AI is asked only when no keyword matches, and even
then it can only name a candidate that the rules check."

---

## Layer 4: Evaluation (how we know it works)

**Say in 60 seconds.** Four kinds of evidence, and one clear gap. (1) Tests: about 1,500 automated tests that run on
every change, including a Postgres database run and Node tests of the web chat. (2) Real-model runs: ten scripted
one-on-one scenes with the real AI models: 0 fallbacks in 94 model calls, no word-limit violations. (3) Speed by
stage on a laptop: one teacher turn is about 2.6 seconds at the median before speech. (4) Retrieval: the right passage
is in the top five for 36 of 40 test questions; 20 of 20 off-topic questions were not answered. **The gap:** nobody has
measured how well the AI coach agrees with human coaches (no figure), no teacher has used it, and the hosted speed
has not been measured. We say so in the README, the QA sheet and the roadmap.

| Evidence | Where | Numbers (measured) |
|---|---|---|
| Tests | `backend/tests/`, `content/tests/`; `make test` | Total in `PROGRESS.md` "Gate totals" |
| Ten live scenes | `eval/one_on_one/LIVE_REPORT.md` | 94 model calls (41 act tagger, 41 child voice, 10 coach, 2 diagnosis), 0 fallbacks, 0 word-cap violations, estimated spend US$0.125 |
| Latency by stage | `docs/PERFORMANCE.md` section 1 (laptop, real models, no speech) | act tagger p50 1385 ms, child voice p50 1236 ms, coach p50 6966 ms / p95 15216 ms |
| Memory | `docs/PERFORMANCE.md` section 2 | 193 MB resident on a Windows laptop (Render free has 512 MB) |
| Retrieval | `eval/retrieval_recall.py`, `docs/PERFORMANCE.md` section 3 | recall@5 0.90 on 40 questions we wrote; 20/20 off-topic rejected |
| My class matcher and classifier | `eval/class_profile/REPORT.md` | 32/32 on 32 sentences we wrote, 0 ids stored for off-list sentences |
| Handbook questions | `backend/tests/unit/test_handbook_questions.py` | Each of the 10 questions finds its own passage in the top 5 |
| Guard corpus | `eval/guards/REPORT.md` | 8 of 8 unsafe test lines blocked |
| Page weight | `scripts/check_first_load.py`, `eval/lowband/REPORT.md` | Chat first load under 150 KB raw (see the report for the current figure) |
| Not done | `eval/calibration/` (the harness exists), `eval/user_testing/` (blank), `eval/stt/` (no recordings) | **No kappa, no user testing, no speech accuracy figure** [UNVERIFIED] |

---

## Layer 5: Output (what the teacher, the ARP and the trainer get)

**Say in 60 seconds.** The teacher gets the child's reply as text and audio, coach feedback that quotes their own
words with one thing to change and an exact sentence to say next time, a tip with a page citation, and a progress
page: an evidence ladder from "practised" to "tried in class", scores over time, and, if they chose a skill to get
better at, a before and after on that skill. The ARP (cluster mentor) gets a weekly digest of **consenting**
teachers only, and escalated questions to answer. The trainer gets counts per module and batch, with any group under
ten hidden, plus the common class struggles and skills teachers chose, also hidden under ten. A coach reviews AI
scores that look unsure. The admin sees latency, guard results and can reset the demo.

| What | Where | Notes |
|---|---|---|
| Teacher chat and pages | `backend/app/web/templates/teacher.html`, `progress.html`, `modules.html`, `class.html` | Server-rendered HTML; Hindi default, English switch |
| Voice replies | `backend/app/speech/tts.py` | Text always arrives; audio when the provider answers |
| ARP digest | `backend/app/web/arp.py`, `backend/app/reports/` | Consenting teachers only |
| Trainer view | `backend/app/web/trainer.py`, `templates/trainer.html` | n < 10 hidden |
| Coach console | `backend/app/web/review.py` | Queue, calibration labelling, move-card review |
| Admin | `backend/app/web/admin.py` | Reset demo, fast-forward timers |
| Works on a weak connection | `backend/app/web/static/sw.js`, `chat.js` | Offline reading, an outbox that resends by itself, lite mode |

**What degrades offline (say this exactly).** Offline, the teacher can read history and the last learning summary and
can write a message that waits in the outbox and sends by itself when the connection returns. Voice notes, the
child's replies, coach feedback, handbook answers and every AI call need the connection; none of those work
offline. On a slow connection, lite mode stops audio downloading until the teacher taps it. If both speech services
fail, the teacher is told to type instead.

---

## The 5-minute walkthrough (what to click and say)

Log in with a free demo account (they are shared; chats reset on login and logout). Passwords are in the submission
form.

| Time | Click | Say |
|---|---|---|
| 0:00 | Open the hosted link. If the page says the server is waking up, wait: free hosting sleeps | "Teachers are trained in teaching moves but never get to practise them. Abhyas is fifteen minutes of practice a week, by voice, in Hindi." |
| 0:30 | `teacher.demo2`: tap the first sample chip (or speak "रवि, तुमने 43 में से 27 कैसे घटाया?...") | "Ravi has a real misconception. He subtracts the smaller digit from the larger. He explains his mistake and answers 24." |
| 1:15 | Send "रवि, सही उत्तर 16 है, इसे याद कर लो।", then "अब नया सवाल: 61 में से 28।" | "If I just tell him, he repeats 16 and makes the same mistake again: 47. The rule engine decides that, not the AI. That is our central claim, and a test enforces it." |
| 2:00 | Tap end practice, read the coach's feedback | "The coach quotes my own words, names one thing to change and gives the exact sentence to say. Every AI output passes a code check first; if it fails twice a template is used." |
| 2:45 | Retry, 1-1, a child, then the diagnosis sentence (see "show me: the diagnosis verdict") | "Before practising, the teacher says what the child's mistake is. Fixed keyword rules decide whether she is right." |
| 3:30 | Menu, Modules, tap a handbook chip on the Modules page | "Answers come only from five official documents, with the page. Off-topic questions are declined." |
| 4:00 | `teacher.demo1`: menu, My class, say "बच्चे हासिल वाले जोड़ में हासिल भूल जाते हैं और गिनती भी कमज़ोर है"; confirm; then choose a skill to get better at | "She tells us where her class struggles and what she wants to improve, from closed lists. The path reorders and the coach leads with her skill. No AI decides what a child says." |
| 4:40 | Go offline (airplane mode), send a message, go online | "It queues and sends by itself." |
| 5:00 | Open `trainer.demo` (log in again) | "The trainer sees counts, groups under ten are hidden, no names." |

---

## The 20 hardest questions, with short honest answers

1. **Is the child an AI?** No. A rule engine decides what the child answers; the AI only phrases the sentence, and a guard rejects any sentence with a number the engine did not choose. `backend/app/rule_engine/engine.py`, `backend/app/llm/guards.py`, test `test_spec_4_5_3_relapse_after_tell`.
2. **What if the AI makes something up?** Every output is checked: structure, then a guard per role, one retry, then a template. For questions, the answer must cite a passage that was retrieved, or the app says "not in my documents". `llm/guards.py`, `eval/guards/REPORT.md` (8 of 8 unsafe test lines blocked).
3. **Have real teachers used it?** No. There are no user-testing results (`eval/user_testing/sessions.csv` is a header only). `docs/submission/MENTOR_SESSION_KIT.md` is how we will get the first. [UNVERIFIED: any outcome claim]
4. **How do you know the misconceptions are realistic?** They come from procedural-bug research on arithmetic mistakes (Brown and Burton 1978; VanLehn 1990, named in `PROGRESS.md` section 1 and the specification). No teacher or FLN coach has rated them; the four move cards are `in_review` in `content/moves/`. The realism survey has not been run. [UNVERIFIED with teachers]
5. **How good is the coach's feedback?** Unmeasured against humans: there is a harness (`eval/calibration/`) but no double coding, so **no kappa figure**. The coach must quote the teacher's words, unsure scores go to a human review queue (`/review`), and a template is used if the model fails. [UNVERIFIED agreement with coaches]
6. **How fast is it on the hosted site?** Not measured on Render. On a laptop with real models and no speech, one teacher turn is about 2.6 s at the median and the coach feedback adds about 7 s (`docs/PERFORMANCE.md`). The target of p95 under 20 s for voice-in to voice-out is not yet measured. [UNVERIFIED hosted]
7. **What happens on 2G or with no connection?** The page is under 150 KB, the chat has an outbox that resends by itself, offline reading, and a lite mode. Voice and every AI step need the connection. A real-phone test has not been run yet (`docs/submission/REAL_DEVICE_CHECKLIST.md`). [UNVERIFIED on a real device]
8. **What if the speech service is rate limited?** A rate-limited provider is skipped for a minute and the next is used; if both fail the teacher is told to type instead. Tests with a fake server, no real quota spent (`backend/tests/unit/test_speech_rate_limit.py`). The hosted deployment needs both providers' keys and `STT_FALLBACK_PROVIDER` set. [UNVERIFIED live]
9. **What does it cost per teacher?** Measured: about US$0.125 of model spend for 10 scenes (about US$0.0125 per scene, `eval/one_on_one/LIVE_REPORT.md`). Speech is priced in `eval/cost/REPORT.md` but not measured. A per-teacher-per-year number needs real usage. [UNVERIFIED]
10. **Where does a teacher's voice go?** It is read into memory, turned into text and dropped; only the text is kept. `backend/app/channels/web.py`; consent text `content/messages_hi.yaml` key `consent_details`. A legal review was not done and we have not audited every code path for retention. [UNVERIFIED]
11. **Who can see a teacher's scores?** Only the teacher until she agrees to share with the ARP; trainers see groups of ten or more, never names. `AGGREGATION_SUPPRESSION_N` in `backend/app/config.py`; tests in `docs/QA_SHEET.md` question 5.
12. **Can a teacher delete her data?** Yes: "मेरा डेटा हटाएँ" or `/teacher/delete`; `backend/app/privacy/purge.py` removes her rows. Tested in `test_class_profile_postgres.py` and the delete tests.
13. **Why search by words and not an AI embedding search?** It is deterministic, needs no external call and was good enough: recall@5 0.90 on 40 questions that we wrote (so not an unbiased estimate). `backend/app/retrieval/search.py`, `docs/PERFORMANCE.md` section 3.
14. **What are the handbook chips?** Four starter questions per teacher per day from `content/handbook_questions.yaml`, each tied to a real passage that a test confirms the search finds. If the answering model is down, the teacher still sees the passage's stored summary with its source page. `backend/app/handbook/`.
15. **Where are the official documents from, and are they accurate?** Five documents: NIPUN Bharat, NCERT Vidya Pravesh, NISHTHA FLN (text layers) and two UP Class 1 guides in Hindi read from page images by an AI step (about 0.2% of words wrong on a 10-page eye check; no human re-check). Citations mark machine-read pages. `content/sources/README.md`.
16. **What is simulated?** The children; the 51 fictional teachers behind the ARP and trainer pages; speech unless keys are set; WhatsApp unless Meta credentials exist. `docs/EVALUATOR_GUIDE.md`.
17. **Does it work on WhatsApp?** The code exists and has unit tests; it has not been run against live Meta accounts, and no number is configured. [UNVERIFIED live]
18. **Does it scale?** Not as built: one process on Render free, in-memory lock and scheduler, 193 MB on a laptop. Scaling needs a shared lock and a job queue; not built. `docs/DEPLOY.md`, `docs/QA_SHEET.md` question 8. [UNVERIFIED beyond a handful of users]
19. **How is this different from a chatbot with the PDFs?** The children's behaviour is a fixed rule engine with deliberate misconceptions and a relapse after being told the answer; the feedback is scored against a rubric and quotes the teacher; and the personalisation is a closed list, never a free decision by a model. `docs/HOW_ARE_WE_DIFFERENT.md`.
20. **Did you write the code?** The team wrote the specification and made the design decisions; an AI coding assistant wrote the code from the specs; a separate reviewer checked each change; automated gates (style, types, about 1,500 tests) run after every change. Review notes and fixes are in `PROGRESS.md`.

### If you are stuck

Say "I do not know; it is not measured yet, and this is where it is written down", then open `docs/QA_SHEET.md` or
`PROGRESS.md`. Never guess a number. The numbers you can quote are in `docs/PERFORMANCE.md`,
`eval/one_on_one/LIVE_REPORT.md` and `eval/class_profile/REPORT.md`.
