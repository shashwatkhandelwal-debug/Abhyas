# Roadmap

Two pages. Each item says whether it is **built** (in this repository and tested), **partly built**, or **intended**
(not built; a plan). Nothing below is a result. Numbers are copied from `docs/PERFORMANCE.md`,
`eval/one_on_one/LIVE_REPORT.md`, `eval/class_profile/REPORT.md` and `eval/cost/REPORT.md`.

## Where we are

Abhyas is a complete demo of the weekly practice loop: learn a move, explain it back, rehearse one-on-one with a
rule-engine child, get coach feedback quoting the teacher, retry, plan to try it in class, reflect. Around it:
a handbook with cited answers, a "My class" step with a closed list of 14 class struggles, a closed list of teaching
skills, and ARP, trainer, coach and admin views with consent and small-group suppression. No real teacher has used it.

## 1. Next practice cases (from the gaps in the FLN training map)

`docs/FLN_TRAINING_MAP.md` maps 14 class-level struggles to what the five ingested documents say. **7 of the 14 have a
practice scene** (served by 4 move cards); **7 have a handbook tip only**. The tip-only ones are the next practice cases,
in this order (reason: the strongest text in the sources, and the commonest in Classes 1 to 3):

| Order | Struggle (no practice case yet) | Why this one | Status |
|---|---|---|---|
| 1 | Counting and number order | Foundation for every numeracy move; NIPUN and the UP Class 1 guide have the strongest text | Intended |
| 2 | Word problems (add or subtract?) | Needs a new kind of child mistake in the rule engine (choosing the wrong operation) | Intended |
| 3 | Letters and sounds | Entry point of the literacy path; NISHTHA and Vidya Pravesh describe the method | Intended |
| 4 | Reading comprehension | Reads aloud but cannot say what it means; needs a one-on-one literacy scene, not only blending | Intended |
| 5 | Comparing numbers | Short scene, reuses the number-line representation | Intended |
| 6 | Small add and subtract facts to 20 | Count-on method; the UP guide gives the steps | Intended |
| 7 | Writing and spelling | Depends on the matra move; the workbook text is not in our sources | Intended |

Class 2 and 3 text is missing from the sources (only the Class 1 UP guides are ingested); adding the Class 2 and 3
guides is a precondition for items 2 and 6. A literacy one-on-one rubric does not exist yet (the matra move is
group-only). Each new case needs the same ingredients as the existing four: a move card, a bug library for the child's
mistake, a rubric, a feedback bank, and tests for the relapse after "telling the answer".

## 2. FLN coach review of the content

- **Built:** the review console at `/review` (queue of unsure AI scores, calibration labelling, move-card review) and the
  kappa harness in `eval/calibration/`.
- **Not done:** all four move cards are `in_review`; no coach has approved them, and the diagnosis keyword sets have not
  been reviewed. There is no kappa figure for the AI coach against human coaches.
- **Intended:** two FLN coaches double-code 20 or more rehearsal transcripts; report quadratic-weighted kappa with the
  sample size and the limitation; fix the rubrics where they disagree. Then coaches approve or edit the cards in `/review`
  (two approvals are required by `MOVE_APPROVALS_REQUIRED` in `config.py`).
- **Intended:** a native Hindi speaker (and a rural-dialect check) reads the children's lines, the coach templates and
  the interface wording; a bias audit of the Hindi output and of the speech recogniser on rural accents is not done.

## 3. Integration pathways

| Pathway | What we can honestly say | Status |
|---|---|---|
| **WhatsApp** | The channel abstraction, Cloud API webhook, templates and the same conversation engine are built and unit-tested; no live Meta account or number is configured | Partly built |
| **NISHTHA / NCERT FLN content** | NISHTHA FLN is one of the five ingested sources (281 passages); the closed lists cite it | Built (as a source) |
| **DIKSHA** | Intended: publish the move cards and handbook questions as DIKSHA-compatible content and sign in through DIKSHA; nothing built; needs DIKSHA onboarding | Intended |
| **SCERT / DIET dashboards** | The trainer view already gives counts per module and batch with n < 10 suppressed, and CSV export; intended: a data feed or API for state dashboards and a Hindi district report | Partly built |
| **ARP workflow** | The weekly digest of consenting teachers and the observation form are built; intended: tie the visit list to existing cluster review schedules | Partly built |
| **Feature phones (IVR)** | Intended; the voice pipeline would be reused, nothing built | Intended |
| **Other languages** | Intended; the message catalogue and content formats are language-separated, speech providers must support the language | Intended |

## 4. Teacher-in-class tracking

- **Built:** a five-step evidence ladder per move (practised, explained, rehearsed, planned, tried in class), a "try in
  class" step with a two-day follow-up, "did it help your class?" after a move that practises her struggle, and a
  before and after on the skill she chose to improve (shown after two scored practices).
- **Intended:** ARP classroom observation tied to the same ladder (the observation form exists and writes evidence);
  optional, consented class-audio coaching; a link from practice to child outcomes. None of this has been tested with
  real classrooms, and no outcome claim is made.

## 5. Cost per teacher, from measured numbers

What is measured: in the ten-scene live run, model spend was about **US$0.125** for 10 scenes (US$0.131 in the
latency run: 41 teacher turns plus 10 coach calls), so **about US$0.0125 to US$0.0131 per rehearsal scene** with Haiku 5.5 for tagging and
the child's words and Sonnet 5.5 for the coach. In rupees at the report's assumed rate of ₹88 per US$ (an assumption in
`eval/cost/REPORT.md`) that is about **₹1.1 to ₹1.2 per scene**.

What is not measured: speech cost (no speech provider was called in those runs), the cost of explain-back checks and
handbook questions, and real usage. Published speech prices in `eval/cost/REPORT.md`: Sarvam speech to text ₹0.50 per
minute, text to speech ₹3.00 per 1,000 characters. A scene of about four teacher turns of 15 seconds each and four
child lines of about 120 characters would add roughly ₹0.5 and ₹1.4. That gives about **₹3 per scene**, an **estimate**
from published prices and our assumed scene length, not a measurement. A per-teacher-per-year figure needs real weekly
usage (scenes per week, retries, questions) and measured speech spend: **not available yet.** The budgets that
cap spend are in `config.py` (`LLM_DAILY_TOKEN_BUDGET`, `SPEECH_DAILY_BUDGET_INR`, `SPEECH_TOTAL_BUDGET_INR`).

## 6. Engineering and scale

- **Not measured:** voice-in to voice-out latency on the hosted deployment (target p95 under 20 s); speed on a real
  low-cost Android phone on 3G or 2G (`docs/submission/REAL_DEVICE_CHECKLIST.md` is ready, all cells empty).
- **Intended:** a shared lock and a job queue so the server can run on more than one instance (today: one process on
  Render free, 193 MB resident on a laptop against a 512 MB limit); move from the free plan before any pilot.
- **Intended:** a speech-accuracy test on recorded rural Hindi voice notes (`eval/stt/` is a harness, with no recordings yet).

## 7. What is simulated and what is real today

| Part | Real | Simulated or missing |
|---|---|---|
| Children's answers | Rule engine, deterministic, tested | The children are not people; their misconceptions come from procedural-bug research, not yet rated by teachers |
| Child wording, coach, answers | Claude calls with guards and fallbacks | Wording quality has not been rated by FLN coaches |
| Handbook | Five official documents, 1,157 passages, page citations | The two Hindi UP guides were read by an AI step and not human-checked |
| ARP and trainer data | The views, consent rules and suppression | 51 fictional teachers whose scores come from the real engine on scripted turns |
| Speech | Providers wired with fallback and rate-limit handling | Mock audio unless provider keys are set; no accuracy measurement |
| WhatsApp | Channel code and tests | No live account |
| Users | Protocol, consent form, mentor kit | No real teacher has used it; no kappa; no realism survey |

## Ask for next steps

1. Two mentor sessions and one FLN coach double-coding session (kits ready).
2. A hosted latency run and a real-phone run with the checklists.
3. A pilot of 20 to 50 teachers through one ARP cluster, with consent, measuring completion and the evidence ladder.
