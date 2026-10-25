# 08 — Conversation flow, state machine, intents, jobs

All teacher-facing strings come from `content/messages_hi.yaml` (seed: `content-seed/messages_hi.yaml`) by key. Never hard-code Hindi text in Python. Message keys referenced below in `monospace`.

## 8.1 Onboarding (`teacher.onboarding_state`)

| State | Bot sends | Expected input → next |
|---|---|---|
| `NEW` | `welcome` (+ audio) + `consent_service` text + buttons [`btn_agree` सहमत हूँ] [`btn_more` और जानें] [`btn_decline` नहीं] | agree → log consent → `JOIN_CODE`; more → `consent_details` then same buttons; decline → `consent_declined`, stay `NEW` |
| `JOIN_CODE` | `ask_join_code` ("आपके ARP ने जो कोड दिया है, वह भेजें। कोड नहीं है तो 'नहीं' लिखें।") | valid code (`invite_code` table → cluster_id, batch_id, district) → `PROFILE_NAME`; "नहीं" → unassigned cluster `UNASSIGNED` → `PROFILE_NAME`. Web demo users skip (pre-mapped) |
| `PROFILE_NAME` | `ask_name` | any text/voice → store first 40 chars → `PROFILE_ADDRESS` |
| `PROFILE_ADDRESS` | `ask_address_form` ("आपको कैसे संबोधित करें?") + buttons [शिक्षिका] [शिक्षक] | → `teacher.address_form` f/m (selects `text_m` message variants) → `PROFILE_EXPERIENCE` |
| `PROFILE_EXPERIENCE` | `ask_experience` + list [0-1 साल, 2-5, 6-10, 10+] | choice → `experience_band`, `first_year = (0-1)` → `PROFILE_CLASSES` |
| `PROFILE_CLASSES` | `ask_classes` + list [कक्षा 1, कक्षा 2, कक्षा 3, कक्षा 1-2, कक्षा 2-3, कक्षा 1-3] | → `classes` → `PLACEMENT_INTRO` |
| `PLACEMENT_INTRO` | `placement_intro` (+ Ravi's first line: "45!" via engine/voice for 52−17) | voice/text → `PLACEMENT` turn 1 |
| `PLACEMENT` | 2 teacher turns with Ravi only (engine placement mode) | after turn 2 → `placement_done` (no score shown, warm message) → compute move path → `READY` |
| `READY` | `ready_first_move` | starts weekly loop at `LEARN` immediately |

Add table `invite_code(code text pk, cluster_id, batch_id, district, active bool)` to the migration; seed `KNP-C01-B1`, `KNP-C01-B2`, `DEMO`.

## 8.2 Weekly loop (`session_state.state`)

| State | On enter (bot sends) | Inputs & transitions |
|---|---|---|
| `LEARN` | `learn_intro` with move title; learn script audio (pre-recorded or TTS, ≤ 2 min) + **text summary** (key points as 4–6 short lines) ; buttons [`btn_understood` समझ गई, आगे] [`btn_replay` फिर से सुनें] | understood → `EXPLAIN_BACK`; replay → resend audio |
| `EXPLAIN_BACK` | `explain_back_prompt` ("अब 1 मिनट में अपने शब्दों में बताइए: इस तरीके में सबसे ज़रूरी क्या है?") ; buttons [`btn_skip` छोड़ें] | voice/text → fidelity_checker → reply (05 §5.7) → `MODEL`; skip → `MODEL` |
| `MODEL` | `model_offer` ; buttons [`btn_listen` सुनें] [`btn_skip` छोड़ें] | listen → send model rehearsal: text transcript (one message, speaker-labelled) + one concatenated audio (voices per speaker) → then `REHEARSE_INTRO`; skip → `REHEARSE_INTRO` |
| `REHEARSE_INTRO` | `rehearse_intro` (scene: class, problem on board, "जब तैयार हों, बच्चों से बात करना शुरू करें। खत्म करने के लिए 'बस' बोलें।") + each child's opening line (engine MISCONCEPTION answers, voiced) | first voice/text → `REHEARSE` (that input is turn 1) |
| `REHEARSE` | — | each input = one teacher turn → SceneRunner (02 §2.2) → child line(s). Stop word / scene end → `FEEDBACK`. Keyword question prefix ("सवाल:", "प्रश्न:") → ASK |
| `FEEDBACK` | coach output: text (strength, change, exact words) + coach audio; if low confidence prefix `coach_low_conf_prefix`; then realism rating list (1–5) ; buttons [`btn_retry` फिर से अभ्यास] [`btn_continue` आगे बढ़ें]. On first completed practice scene, appends score-sharing consent buttons [`btn_share_arp` ARP से साझा करें] [`btn_share_not_now` अभी नहीं] (opt-in default: false; togglable anytime from My class or menu). | retry (if `rehearse_attempts < MAX_REHEARSAL_RETRIES_PER_WEEK` (3)) → new scene → `REHEARSE_INTRO`; else `retry_limit` → continue; continue → `TRY_IN_CLASS`. Rating → `realism_rating` |
| `TRY_IN_CLASS` | `try_in_class` + peer checklist (numbered) + 2 reflection questions ; buttons [`btn_peer` साथी ने देखा] [`btn_self` खुद बताऊँगी] [`btn_later` बाद में] ; schedule `followup_try_in_class` +72 h | peer → `REFLECT_PEER`; self → `REFLECT_SELF`; later → stay (reminder job) |
| `REFLECT_PEER` | each checklist item with [हाँ] [नहीं] buttons, one at a time | after last → evidence level 3 → `DONE` |
| `REFLECT_SELF` | reflection Q1, then Q2 (voice/text) | after Q2 → evidence level 2 → `DONE` |
| `DONE` | `week_done` summary (evidence level reached, next move title) ; buttons [`btn_next_move` अगला तरीका] [`btn_progress` मेरी प्रगति] | next move: starts next week's move now (demo-friendly) |

**Evidence:** completing `REHEARSE` (scene ended with ≥ 3 teacher turns) → level 1. Higher levels from REFLECT / ARP observation. `adoption_evidence` keeps all rows; views show the max level per teacher × move.

**Resume rule:** any inbound after > 6 h of inactivity in a mid-week state → `resume_prompt` ("आप {state_name_hi} पर थीं। आगे बढ़ें?") + buttons [आगे बढ़ें] [शुरू से].

## 8.3 Intents (checked in this order, `core/intents.py`)

1. **Button id** → direct.
2. **Global keywords** (normalised, whole-message or prefix match):

| Intent | Keywords (Hindi / Hinglish / English) | Effect |
|---|---|---|
| help | मदद, help, menu, मेनू | `help_menu` (list: आगे बढ़ें, प्रश्न पूछें, मेरी प्रगति, लाइट मोड, सहमति बदलें) |
| stop_scene | बस, रुको, खत्म, stop, bas (REHEARSE only) | end scene → FEEDBACK |
| next | आगे, अगला, शुरू, next, start, aage, shuru | advance where allowed (template quick-reply payloads "शुरू"/"आगे" land here) |
| skip | छोड़ें, skip, chhodo | skip skippable step |
| repeat | फिर से, दोबारा, repeat, phir se | resend last bot prompt |
| ask | सवाल, प्रश्न, question, sawal (+ optional text) | ASK flow |
| lite_toggle | लाइट मोड, lite | toggle `lite_mode` (text-only replies) |
| progress | प्रगति, progress | progress summary |
| consent | सहमति, consent | consent settings flow |
| delete | मेरा डेटा हटाएँ, delete my data | confirm → purge → `data_deleted` |

3. **State-specific expectation:** in `EXPLAIN_BACK`, `REFLECT_SELF`, `PROFILE_NAME`, `PLACEMENT`, `REHEARSE` the input is taken as the step's answer **without** calling intent_router (REHEARSE: always a teacher turn).
4. Otherwise → `intent_router` (05 §5.3).

STT low confidence (06) → `stt_confirm` "मैंने सुना: '{text}'. सही है?" [हाँ] [फिर से बोलूँगी] — except in REHEARSE where low-confidence turns proceed but are flagged in the transcript.

## 8.4 ASK flow

`prior_state = state; state = ASK` → question_classifier → (optional one clarifying question → wait) → retrieval → guide_answerer or escalation (05 §5.8) → send answer → `ask_resume` + re-send prior state's prompt → `state = prior_state`. Questions during onboarding are answered then onboarding resumes.

## 8.5 Personal move path (`sessions/path.py`)

Deterministic score per move (lower = sooner), recomputed after placement and after each week:
```
score = month_rank(move.sankul_month vs current month; current month = 0, next = 1, …)*10
      − 15 if placement used tell_answer and move.effective has ask_to_explain
      − 10 if teacher.classes contains 1 and move.domain == literacy or move.id startswith NUM_PLACE_VALUE
      − 5 * (2 − min rubric score on this move's criteria in last attempt)   # revisit weak moves (only for moves already done)
      − 8 if teacher asked a question whose category matched move.tags
      + 100 if move already DONE with evidence ≥ 2
first_year teachers: fixed induction order from content/induction_track.yaml (seed: place value → subtraction → addition → reading)
```
Store top order in `move_path` with `reason` text.

## 8.6 Scheduled jobs (`jobs/`)

APScheduler interval tick every 60 s pulls due rows from `scheduled_job` (status pending, run_at ≤ now) with `FOR UPDATE SKIP LOCKED`; cron-style recurring jobs are created by a daily "planner" job.

| Kind | When | Action |
|---|---|---|
| `weekly_prompt` | Monday 09:00 IST per active teacher in `DONE` or with no session this week | create session_state for next move in path (`LEARN`); send `tpl_weekly_move` template if outside window else freeform `weekly_move` |
| `reminder` | 72 h after last state change if not `DONE` (max 1 per week) | `tpl_reminder` / `reminder` |
| `followup_question` | +48 h after an answered question | `tpl_followup_question` "क्या {topic} वाला सुझाव काम आया?" [हाँ] [नहीं] [अभी नहीं] → `question.followup_result`; "हाँ" → evidence level 2 for linked move if any |
| `followup_try_in_class` | +72 h after entering TRY_IN_CLASS | `tpl_try_in_class_followup` |
| `arp_digest` | Saturday 17:00 IST per ARP | build digest snapshot; send `tpl_arp_digest` with link `/arp` |
| `aggregates` | nightly 02:00 IST | recompute `agg_module_batch` |
| `retention_purge` | nightly 03:00 IST | 3.4 |

`POST /admin/fast-forward/{teacher_id}` sets that teacher's pending jobs `run_at = now()` and ticks immediately. Tests use a fake clock (`freezegun` or injected `Clock`).

## 8.7 Sankul mode (minimal in this build)

ARP page has "संकुल अभ्यास शुरू करें" → generates a 6-char session code; any teacher who sends `संकुल <code>` joins a shared scene (mode `sankul`) for the month's move where turns from any member's phone drive one scene; the ARP's page shows the live transcript. If time is short (see 14), implement as: ARP starts a scene from the web on one phone (normal web chat logged in as ARP with role-play enabled) and logs one observation per attending teacher. Mark which version shipped in `PROGRESS.md`.

## 8.8 State machine tests (`tests/unit/test_state_machine.py`)

- Every (state, input-kind/intent) pair in 8.1–8.4 → expected next state and message keys (table-driven, 100% transition coverage; generate the table from the state machine definition and assert every edge is exercised).
- ASK from every weekly state resumes the same state and re-sends its prompt.
- Retry limit enforced at 3.
- 24-h window: weekly_prompt uses template when `last_inbound_at` > 24 h ago, freeform otherwise.
- Delete flow purges and the next inbound starts at `NEW`.
- Full happy path run (MockLLM, MockSTT text inputs) from `NEW` to `DONE` in one test, asserting evidence level 2 or 3 recorded.
