# Abhyas — Build Specification (ARCHITECTURE.md)

> **For the coding agent.** This file is the single source of truth for building Abhyas. Read it fully before writing code. Build in the milestone order in §16. Every module has acceptance criteria; a milestone is done only when its tests pass. Where this file says **HUMAN INPUT**, stop and ask rather than invent data, credentials or licences.

Team Asymptotes · AI for Foundational Learning Hackathon 2026 · Challenge 3: Teacher Support and Training

---

## 0. What we are building (one paragraph)

A **voice-first WhatsApp practice partner** for government primary teachers (FLN, Classes 1–3) between trainings, in Hindi. Each week a teacher: **learns** one teaching "move" from the state FLN module (2-min voice note), **explains it back** in her own words (1-min voice note, scored for fidelity), **hears a model teacher** handle the scenario, **rehearses** it by voice with **three AI-simulated children** whose mistakes are **computed by a rule engine** (Claude only voices the lines), gets **rubric feedback** (one strength, one change, exact words to try) and **retries**, then **tries it in class** (peer 5-minute checklist or guided reflection), and can **ask questions any time** (answers cite state guides; follow-up after 2 days; hand-off to the ARP). The backend produces an **evidence ladder** per move per teacher, a **weekly ARP digest**, and a **trainer view** (DIET/SCERT) showing fidelity and adoption by module and training batch (groups of ≥ 10 only).

### Non-negotiable constraints

| Constraint | Value |
|---|---|
| Channel | WhatsApp Business Cloud API (via a BSP such as Gupshup); nothing to install |
| Language | Hindi and Hinglish, voice first; text accepted |
| Teacher time | ~15 min/week |
| Latency | voice note in → voice reply out **< 20 s for 95% of turns** |
| Child answers | **Always from the rule engine. Never from the LLM.** |
| Audio | deleted after transcription |
| Privacy | teacher data private by default; **no individual scores go upward without the teacher's consent**; trainer view aggregates only groups ≥ 10 |
| Class audio | **off by default** (records children) |
| Claude output | always JSON against a schema; code guards validate before anything is sent |

---

## 1. Repository layout (monorepo)

```
abhyas/
├── ARCHITECTURE.md
├── backend/                         # Python 3.11, FastAPI
│   ├── app/
│   │   ├── main.py                  # FastAPI app, routers
│   │   ├── config.py                # env + all thresholds (no magic numbers)
│   │   ├── whatsapp/                # webhook, signature verify, send, templates, media
│   │   ├── speech/                  # stt.py, tts.py (provider adapters)
│   │   ├── sessions/                # state machine, weekly loop, timers
│   │   ├── rule_engine/             # child personas, misconception rules, state transitions
│   │   ├── llm/                     # Claude client, 5 role prompts, JSON schemas, guards
│   │   ├── retrieval/               # pgvector search over guides + practice library
│   │   ├── scoring/                 # rubric scoring, explain-it-back scoring, evidence ladder
│   │   ├── reports/                 # ARP digest, trainer aggregates
│   │   ├── db/                      # SQLAlchemy models, Alembic migrations
│   │   └── jobs/                    # scheduled jobs (weekly prompts, follow-ups, digests)
│   └── tests/
├── content/                         # Python: Claude content pipeline + validators
│   ├── sources/                     # state FLN modules, UP teacher guides, NIPUN (HUMAN INPUT)
│   ├── moves/                       # generated + approved move cards (YAML)
│   ├── personas/                    # child personas (YAML)
│   ├── rules/                       # misconception rules as Python + tests
│   ├── schemas/                     # JSON Schemas
│   ├── pipeline/                    # generate -> validate -> review -> publish
│   └── tests/
├── review-console/                  # web: FLN coaches approve content, review queue
├── trainer-view/                    # web: DIET/SCERT aggregates (read-only)
├── eval/                            # coach calibration, latency, realism survey
└── infra/                           # docker-compose, worker, deployment
```

Stack: FastAPI, Uvicorn, SQLAlchemy 2 + Alembic, Supabase Postgres with **pgvector**, Redis (or Postgres-backed) job queue (RQ/Arq/Celery—pick one), httpx, pydantic v2, pytest. Web views: minimal React or server-rendered HTML.

---

## 2. System overview

```
BUILD (cloud, once per content release)
  State FLN modules, UP teacher guides, NIPUN guidance
    -> Claude drafts move cards, key points, rubrics, model scripts
    -> validators + second Claude review + FLN coaches approve
    -> Move library (Postgres + pgvector)
  Research on children's maths and reading errors
    -> Claude drafts error rules as tested code; child personas
    -> unit tests; 100 double-coded rehearsals calibrate the coach
    -> Rule engine and coach rubrics (versioned release)  -> released to server

RUN (every WhatsApp turn, reply in seconds)
  Teacher voice note -> Speech to text -> Session manager (step, state, rule engine)
    -> Claude in five roles + text to speech -> voice reply (next line / feedback / retry)

REPORT (background, weekly and on demand)
  Practice log + evidence ladder (audio deleted) -> Supabase (RLS)
    -> ARP weekly digest; trainer view by module (groups of 10+)
    -> unanswered questions, low-confidence scores -> expert review queue
    -> new moves, rules and answers for next release
```

---

## 3. Domain model

```python
class Move(BaseModel):                     # one teachable practice
    id: str                                # e.g. "NUM_BUNDLES_PLACE_VALUE"
    domain: Literal["numeracy", "literacy"]
    title_hi: str
    module_ref: SourceRef                  # state module + page/section
    sankul_month: str | None               # month it is the Shikshak Sankul topic
    key_points: list[KeyPoint]             # 4–6, used for explain-it-back
    teaching_acts_effective: list[str]     # act tags that address the target causes
    target_causes: list[str]               # misconception ids this move fixes
    rubric: Rubric                         # 3–5 criteria, 0–2 each
    learn_script_hi: str                   # 2-min voice note script
    model_rehearsal: list[ScriptLine]      # model teacher with the same 3 children
    scenario: Scenario                     # problem(s), personas
    peer_checklist: list[str]              # 5-minute class checklist
    reflection_questions: list[str]        # 2 questions

class KeyPoint(BaseModel): id: str; text_hi: str; must_have: bool
class Rubric(BaseModel): criteria: list[Criterion]
class Criterion(BaseModel): id: str; text: str; levels: dict[int, str]  # 0,1,2 descriptors

class Persona(BaseModel):                  # an AI child
    id: str; name: str; grade: int; voice_id: str
    misconceptions: list[str]              # rule ids, e.g. ["SUB_SMALLER_FROM_LARGER"]
    temperament: Literal["shy", "confident", "distracted"]
    speech_style_hi: str                   # short style note for voicing only

class TeachingAct(str, Enum):              # fixed taxonomy; Claude tags teacher turns with these
    ASK_TO_EXPLAIN = "ask_to_explain"
    CONCRETE_REPRESENTATION = "concrete_representation"   # bundles/sticks, objects
    PROBE_WITH_SIMPLER_CASE = "probe_simpler_case"
    CONTRAST_TWO_ANSWERS = "contrast_answers"
    MODEL_STEP_ALOUD = "model_step_aloud"
    TELL_ANSWER = "tell_answer"
    REPEAT_QUESTION = "repeat_question"
    PRAISE_EFFORT = "praise_effort"
    PRAISE_GENERIC = "praise_generic"
    SCOLD = "scold"
    INVOLVE_PEER = "involve_peer"
    PHONICS_SOUND_OUT = "phonics_sound_out"
    OFF_TASK = "off_task"
```

Initial library: **12 numeracy + 4 literacy moves** (e.g. bundles for place value, asking children to explain, grouping by level, phonics routines). **HUMAN INPUT:** the actual state module PDFs and guides.

---

## 4. The weekly loop (session state machine)

States per teacher per week (persist in `session_state`):

```
PLACEMENT (first time only)
  -> LEARN            send learn voice note for this week's move
  -> EXPLAIN_BACK     wait for 1-min voice note; score vs key points
  -> MODEL            send model rehearsal audio
  -> REHEARSE         multi-turn scene with 3 AI children (§5)
  -> FEEDBACK         coach feedback; offer RETRY (back to REHEARSE) or continue
  -> TRY_IN_CLASS     send peer checklist / reflection prompt
  -> REFLECT          receive checklist result or 2 reflection answers
  -> DONE             update evidence ladder
ASK (any state, interrupt): handled by §8, then resume prior state
```

Rules:
- Any state accepts free questions → route to ASK, then resume.
- Teacher may skip MODEL; may retry REHEARSE up to 3 times per week.
- WhatsApp **24-hour customer-service window**: business-initiated messages outside it must use **approved utility templates** (weekly prompt, follow-up, reminder). Track `last_inbound_at` per teacher.
- **Placement** (first contact): short role-play with one AI child + 3 questions (experience years, first-year yes/no, classes taught). Output: `experience_band`, `first_year`, `class_needs`, initial move order.
- **Personal path**: move order = state/Sankul month order, re-ranked by placement result, lowest rubric scores, explain-back gaps, and topics of her own questions. First-year teachers get a year-long induction track.
- **Sankul mode**: at the monthly Shikshak Sankul meeting, the ARP can start the month's move for a group (rehearse together, one phone). The ARP later logs an observation of the practised move.

Acceptance: state machine has 100% transition test coverage; resumes correctly after ASK interrupts; template-vs-session message choice tested against the 24-hour rule.

---

## 5. Rehearsal with AI children (core IP)

**Principle: mistakes are computed, not improvised.** LLMs asked to play students tend to solve problems correctly or give in too quickly (Markel et al., 2023; "Simulating Students or Sycophantic Problem Solving?", arXiv 2605.12748, 2026). So:

### 5.1 One teacher turn
1. **STT** → transcript (Hindi/Hinglish).
2. **Act tagger** (Claude role, JSON): returns `{acts: [TeachingAct], addressed_child: persona_id|null, quote: str}`.
3. **Rule engine** (pure Python, deterministic): given scenario, each child's `ChildState`, and acts → returns for the addressed (or next) child `{answer, reasoning_steps, state_change, affect}`.
4. **Child voice** (Claude role, JSON): renders one short Hindi line for that child from the structured result + persona style. **Guard**: extract every number/Devanagari word token from the line; every number must equal `answer` or appear in `reasoning_steps`; line ≤ 25 words; must not contain the correct answer unless state is `CORRECT`. On failure → retry once → else use a template line.
5. **TTS** in the child's voice → send audio.

### 5.2 ChildState and transitions
```python
class ChildState(Enum):
    MISCONCEPTION = 0      # applies bug rule, confident
    CAN_EXPLAIN = 1        # still wrong, but explains steps (reveals the bug)
    PARTIAL = 2            # corrects with scaffold, may relapse on a new item
    CORRECT = 3            # correct and explains why

TRANSITIONS = {
  # act tag -> effect on a child whose misconception is in move.target_causes
  "ask_to_explain":          {MISCONCEPTION: CAN_EXPLAIN},
  "concrete_representation": {CAN_EXPLAIN: PARTIAL, MISCONCEPTION: PARTIAL},
  "probe_simpler_case":      {CAN_EXPLAIN: PARTIAL},
  "contrast_answers":        {PARTIAL: CORRECT},
  "model_step_aloud":        {PARTIAL: CORRECT},
  "tell_answer":             "PARROT",   # child repeats answer now, relapses on next item
  "repeat_question":         "NO_CHANGE",
  "scold":                   "SHY",      # shy persona goes silent one turn
}
```
- A child improves **only** when an act in `move.teaching_acts_effective` addresses that child's cause. Telling the answer yields a correct echo followed by the **same bug on the next item** (tests transfer).
- Maths answers come from `content/rules/*.py` (same bug-rule format as Sudhaar, e.g. `SUB_SMALLER_FROM_LARGER(52,17) = 45`). Reading errors come from reading-error rules (matra drop, first-akshar guess, akshar-by-akshar).
- Scene ends when all three children reach `CORRECT`, or 8 teacher turns, or teacher sends "बस" / "stop".

**Worked example (must be a test):** Ravi has `SUB_SMALLER_FROM_LARGER`. Teacher: "Ravi, 52 mein se 17 kaise ghataya? Batao." → act `ask_to_explain` → Ravi `CAN_EXPLAIN` → line conveys "2 mein se 7 nahi hota, to 7 mein se 2 kiya. 45!" (numbers 2, 7, 45 verified). Next teacher act `concrete_representation` (5 bundles, 2 sticks) → `PARTIAL`.

### 5.3 Coach feedback (after scene)
Claude role **coach**, input: full transcript, act tags, state trajectory, move rubric. Output JSON:
```json
{"scores": {"criterion_id": 0|1|2}, "evidence": {"criterion_id": "quote"},
 "strength_hi": "...", "change_hi": "...", "exact_words_hi": "...", "confidence": 0.0}
```
Guards: every score must cite a quote that appears in the transcript; one strength, one change, one exact-words line; ≤ 60 words spoken. `confidence < 0.6` → queue for expert review (still send feedback, marked lighter). Then offer **retry**.

Calibration: 100 rehearsals double-coded by FLN coaches; target **Cohen's kappa ≥ 0.7** AI vs coaches. Store calibration set in `eval/calibration/`.

---

## 6. Explain it back (fidelity)

Input: teacher's 1-min explanation transcript + move key points.
Claude role **fidelity checker** → JSON:
```json
{"points": [{"id": "kp1", "status": "covered|partial|missing", "quote": "..."}],
 "misconceptions": ["..."], "confidence": 0.0}
```
Guard: every `covered/partial` needs a quote present in the transcript. Reply to teacher with a short confirmation and the one missing point. Aggregate by **module × training batch**, shown only when **n ≥ 10**. Target kappa ≥ 0.7 vs coaches.

---

## 7. Evidence ladder (adoption)

Per teacher × move, record the **strongest** evidence, labelled honestly:

| Level | Source |
|---|---|
| 1 Rehearsed | completed REHEARSE |
| 2 Self-reported | reflection answers |
| 3 Peer-observed | colleague's 5-min checklist |
| 4 ARP-observed | ARP logs observation on visit |
| 5 Children improved | short class check linked to the move (optional; from partner tools such as VallamAI if available) |

Trainers see **adoption, not attendance**.

---

## 8. Ask any time (guide answerer)

1. Classify: pedagogy / classroom management (two grades, absences, noise, no materials, parents) / admin / out of scope.
2. If ambiguous → **one clarifying question first**.
3. Retrieve top-k chunks from pgvector over **state guides + reviewed practice library**.
4. Claude role **guide answerer** → JSON `{answer_hi, source_ids[], confidence}`. Guard: at least one `source_id` from retrieved set; answer ≤ 80 spoken words; cite source by short name in reply.
5. If no chunk above similarity threshold or confidence low → "मैं आपके ARP से पूछकर बताती हूँ" → add to **review queue** and ARP digest.
6. Schedule **follow-up after 2 days** (utility template): "Did it work?" → answer feeds evidence ladder.

---

## 9. Claude roles (all in `backend/app/llm/`)

| Role | Input | Output schema | Guard |
|---|---|---|---|
| act_tagger | teacher turn transcript, scene context | acts[], addressed_child, quote | acts ∈ taxonomy |
| child_voice | rule-engine result, persona | line_hi | numbers match rule output; length; no leaked correct answer |
| model_teacher | move, scenario | script lines (build-time only) | reviewed by coaches before release |
| coach | transcript, acts, trajectory, rubric | scores, evidence, strength, change, exact_words, confidence | quotes exist; single strength/change |
| fidelity_checker | explanation, key points | points[], misconceptions, confidence | quotes exist |
| guide_answerer | question, retrieved chunks | answer_hi, source_ids, confidence | sources ⊆ retrieved |

Config: `CLAUDE_MODEL` env var; `ANTHROPIC_API_KEY` (**HUMAN INPUT**). Use tool/JSON-schema output; temperature low for scoring roles. Log prompt version + model per call. Timeout 8 s; one retry; fall back to template text.

---

## 10. Speech

- **STT**: AI4Bharat IndicConformer (self-hosted, GPU/CPU) **or** a hosted Indian speech API — adapter interface `transcribe(audio_bytes, lang_hint) -> Transcript{text, words, confidence}`. WhatsApp voice notes arrive as OGG/Opus; convert with ffmpeg to 16 kHz mono.
- **TTS**: Indian-language TTS (e.g. AI4Bharat Indic Parler-TTS) with **distinct voices** for 3 children, model teacher and coach; **recorded lines** for fixed prompts (learn scripts, templates). Output OGG/Opus for WhatsApp.
- Cache TTS for identical lines.
- Audio **deleted after transcription**; only transcripts stored.

**HUMAN INPUT:** choice of STT/TTS provider and credentials, or GPU host.

---

## 11. WhatsApp integration (`backend/app/whatsapp/`)

- Webhook: verify signature; handle text, audio, interactive button replies; idempotent on message id.
- Media: download voice note → STT; upload TTS audio → send.
- Interactive buttons for choices (retry / continue / skip model).
- **Templates** (utility category) for: weekly move prompt, follow-up after 2 days, reminder, ARP digest. Teacher-started conversations are free; utility templates cost ~₹0.12 each in India (Meta, 2026) — log count per week for cost report.
- Rate-limit and queue outbound sends.

**HUMAN INPUT:** WhatsApp Business account, phone number, BSP credentials, approved template names.

Roadmap (not in build scope): IVR phone-call version for basic phones.

---

## 12. Data model (Postgres, Alembic)

```sql
create extension if not exists vector;

create table teacher(id uuid primary key, phone_hash text unique, name text, school_id text,
  cluster_id text, block_id text, district text, batch_id text, experience_band text,
  first_year bool, classes int[], consent_share_scores bool default false,
  consent_class_audio bool default false, created_at timestamptz);
create table arp(id uuid primary key, name text, cluster_id text, phone_hash text);
create table move(id text primary key, version text, domain text, payload jsonb, sankul_month text);
create table persona(id text primary key, version text, payload jsonb);
create table rule(id text primary key, version text, kind text, code_ref text);
create table session_state(teacher_id uuid, week date, move_id text, state text,
  retries int default 0, last_inbound_at timestamptz, context jsonb, primary key(teacher_id, week));
create table turn(id uuid primary key, teacher_id uuid, week date, role text, transcript text,
  acts text[], child_id text, rule_result jsonb, latency_ms int, created_at timestamptz);
create table rehearsal_score(id uuid primary key, teacher_id uuid, move_id text, attempt int,
  scores jsonb, evidence jsonb, confidence real, created_at timestamptz);
create table explain_score(id uuid primary key, teacher_id uuid, move_id text,
  points jsonb, misconceptions text[], confidence real, created_at timestamptz);
create table adoption_evidence(teacher_id uuid, move_id text, level int, source text,
  detail jsonb, created_at timestamptz);
create table question(id uuid primary key, teacher_id uuid, text text, category text,
  answer text, source_ids text[], confidence real, status text, followup_at timestamptz);
create table doc_chunk(id text primary key, source text, section text, text text,
  embedding vector(1024));
create table review_item(id uuid primary key, kind text, ref_id uuid, reason text, status text);
```
RLS: teachers see only own rows (via bot, not direct); ARPs see their cluster's digest fields only for teachers with `consent_share_scores`; trainer view reads **pre-aggregated** tables with n ≥ 10.

---

## 13. Reports

- **ARP weekly digest** (WhatsApp template + link): which teachers practised which move, who asked for help, unanswered questions, suggested visit list (who struggled on which move — consenting teachers only).
- **Trainer view** (DIET/SCERT, web): by module × batch — explain-back key points most often missing, rehearsal rubric distributions, evidence-ladder distribution, activity rates. Suppress groups < 10.

---

## 14. Content pipeline (`content/pipeline`)

Generate (Claude, JSON Schema) → scripts validate (every key point traceable to a source section; numbers in scenarios verified by rules; rule tests pass; Hindi NFC; length) → second Claude pass against rubric → **two FLN coaches approve** in review console → publish versioned release to DB. Rubrics and model scripts co-written with **2–3 FLN coaches**. Unanswered questions and low-confidence scores feed the next release.

---

## 15. Evaluation targets

| Metric | Target | Method |
|---|---|---|
| AI coach vs expert coaches | kappa ≥ 0.7 | 100 double-coded rehearsals |
| Explain-it-back scoring vs coaches | kappa ≥ 0.7 | coded sample |
| Realism of AI children | ≥ 4 of 5 teacher rating | post-rehearsal button |
| Weekly active teachers | ≥ 50% over 6 weeks (nudge baseline 15–20%) | logs, pilot of 20–30 teachers via partner NGO + ARP |
| Latency | < 20 s for 95% of turns | `turn.latency_ms` |

Report all targets honestly, including misses.

## 16. Milestones (build in order)

| # | Milestone | Done when |
|---|---|---|
| M1 | Scaffold, DB migrations, config, WhatsApp webhook echo (text + audio round trip) | echo test passes on sandbox number |
| M2 | Rule engine + personas + transitions, fully unit-tested (no LLM) | Ravi worked example passes; relapse-after-tell test passes |
| M3 | STT/TTS adapters + Claude roles with schemas and guards; rehearsal loop end to end | one scene runs < 20 s p95 in load test |
| M4 | Session state machine, weekly loop, templates, 24-h window logic, ASK routing + retrieval | state tests green |
| M5 | Content pipeline + review console; first 4 moves approved | release published |
| M6 | Scoring: coach, explain-back, evidence ladder; calibration harness | kappa report generated |
| M7 | ARP digest + trainer view with suppression | n<10 suppression test passes |
| M8 | Pilot tooling: consent flows, cost log, eval report | report in `eval/` |

## 17. Privacy and safety (enforce in code)

- Teacher consent at onboarding; private by default; `consent_share_scores=false` blocks all individual data upward.
- Class audio off by default; enabled only where the school runs Abhyas as its own tool with parents informed; deleted after scoring.
- Children never scored or identified.
- DPDP Act 2023 and Rules 2025.
- Children's mistakes never generated by the LLM; LLM outputs always schema-validated and guarded.

## 18. Conventions
ruff + mypy strict; pydantic models at every boundary; all thresholds in `config.py`; every Claude prompt versioned in `llm/prompts/` with a golden-output test; Hindi text NFC-normalised.
