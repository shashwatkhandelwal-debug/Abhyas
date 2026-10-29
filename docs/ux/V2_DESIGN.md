# Abhyas v2 (national) — design note

Written from reading the code on branch `feat/v2-national` (cut from `main` @ `62014e5`, tag `pre-v2-build`). No code is changed by this note. Everything below is what the files say today; where I am inferring, it says "assumed". Line numbers are from this checkout and will drift.

## 1. How the current system works

### 1.1 Quick replies, onboarding, idle state, "next action"
- An outbound message is `OutboundMessage` (`backend/app/core/types.py:41`): `kind` text/audio/buttons/template, `buttons: list[Button]` **max 3**, `citations`, `speaker`. Quick replies are therefore server-driven: a service method returns buttons, the web channel and WhatsApp render them, a tap comes back as `inbound.button_id`.
- `SessionService._handle_inbound` (`sessions/service.py:805`) is the single entry. Order: intent match (`core/intents.py`, `BUTTON_INTENT_MAP`) → inactivity resume rule (>6 h in a mid-week state asks continue/restart, ~l.825) → delete confirm → training rating (`_handle_training_rating`) → "My class" and teaching-skill flows (~l.876–900, only when onboarding is READY) → onboarding or weekly state machine.
- Onboarding is `OnboardingStateEnum` (`sessions/state_machine.py`): NEW → JOIN_CODE → PROFILE_NAME → PROFILE_ADDRESS → PROFILE_EXPERIENCE → PROFILE_CLASSES → SHARE_CONSENT → PLACEMENT_INTRO → PLACEMENT → READY (branches at `service.py:1149–1340`). PROFILE_ADDRESS stores `teacher.address_form` (`f`/`m`, DB check constraint in `db/models.py:99`); it is carried in `SessionContext.address_form` and passed to `get_message(key, address_form)`, which picks `text_m` when `m` (`core/messages.py`).
- Weekly state: `SessionStateEnum` LEARN → EXPLAIN_BACK → MODEL → REHEARSE_INTRO/REHEARSE → FEEDBACK → … → REFLECT_PEER/SELF → DONE (+ ASK). After DONE, `_after_*` helpers offer buttons `btn_next_move` / `btn_progress` (`service.py:410–440`). The "idle" state is READY + DONE or LEARN; there is no separate idle screen — a message in DONE routes through the intent router (handbook question, next move, progress).
- "Next action" prompt: `web/next_action.py::next_action()` is a **pure function of saved state** returning `{key, text, suggest}`; it is the one sentence above the composer. It maps onboarding stage → `ONBOARDING_HINTS`, weekly state → `WEEKLY_HINTS`, setup stage → `SETUP_STAGE_HINTS`, and checks in-progress sub-flows (`class_stage`, `skill_stage`, `rating_stage`, `module_check_stage`) first. Text lives in catalog keys `hint_*`. Any new multi-step flow needs one `hint_*` key and one branch here.
- Sub-flow pattern to copy: `class_profile/flow.py` and `class_profile/skills_flow.py` (`start`, `handle` returning `FlowResult(messages, handled, saved)`), state kept as a stage string on `SessionContext` (`class_stage`, `skill_stage`) and persisted in `session_state.context` JSONB.

### 1.2 `content/class_struggles.yaml` — 14 struggles
Each has `id`, labels, tip, `chunk_ids` (2 each, all citing stored handbook chunks) and an optional `move_id`. Loaded by `class_profile/library.py` (`load_library`). Chosen ids live in `teacher.class_struggles` (JSONB, max `STRUGGLE_MAX_CHOSEN`); an "other" entry is the no-match fallback.

| struggle id | move_id |
|---|---|
| NUM_COUNTING | none |
| NUM_NUMBER_WRITING | NUM_PLACE_VALUE_BUNDLES |
| NUM_PLACE_VALUE | NUM_PLACE_VALUE_BUNDLES |
| NUM_COMPARE | none |
| NUM_ADD_CARRY | NUM_ADD_CARRY_BUNDLES |
| NUM_SUB_REGROUP | NUM_SUB_REGROUP_BUNDLES |
| NUM_WORD_PROBLEM | none |
| NUM_SMALL_FACTS | none |
| LIT_MATRA_DROP | LIT_MATRA_BLENDING |
| LIT_AKSHAR_BY_AKSHAR | LIT_MATRA_BLENDING |
| LIT_FIRST_AKSHAR_GUESS | LIT_MATRA_BLENDING |
| LIT_LETTER_SOUND | none |
| LIT_COMPREHENSION | none |
| LIT_WRITING | none |

So 6 of 14 map to one of the 4 moves; **8 have a tip and citations but no practice move** — any feature that says "practise this" must say so honestly for those 8 (see §3).

### 1.3 Content chunks, retrieval, citations
- `content/chunks/*.jsonl`: 6 files, 1,157 chunks (nipun 294, up_bhasha 325, nishtha 281, up_ganit 168, vidya_pravesh 67, seed_from_moves 22). Each row has `chunk_id`, `source_id`, `source_short_hi`, `page`, `text`, `lang`, headings.
- `retrieval/search.py::GuideRetriever` is in-process BM25 (rank_bm25) over those files with Hindi tokenising/stemming; `get_guide_retriever()` is a cached singleton. No DB, no embeddings, no network.
- Citation line: `llm/roles/guide_answerer.py::format_guide_citation(source_short_hi, page, address_form)` and `citations_for_chunks(chunks)` → `core/types.Citation(chunk_id, source_short_hi, page, line_hi)`; the web UI makes it tappable (`chat_api.get_source_excerpt`). Class-struggle tips cite via `class_profile/flow.py::source_line(chunk_ids, address_form)`.
- Handbook questions with no good chunk fall back through `handbook/fallback.py` / `content/handbook_questions.yaml`.

### 1.4 Coach rubric and feedback path
- Rubric and feedback bank live in each move YAML (`content/moves/*.yaml`: `rubric`, `feedback_bank` with `strength_hi/en`, `change_hi/en`, `exact_words_hi/en`).
- `llm/roles/coach.py`: `coach_feedback()` (LLM, schema- and guard-checked) with `fallback_coach_feedback()` (deterministic, used when LLM is off or guards fail). Scores come from the rule-engine/scoring side (`backend/app/scoring`), never from the child lines. The strength is only shown as evidenced if the best criterion scored ≥1 and the quote is among the teacher's actual turns (`coach.py:~250`); in one-on-one the teacher's own words are appended with the catalog key `coach_quote_suffix` (`«{quote}»`, capped by `COACH_QUOTE_MAX_WORDS`). Group scenes carry no quote.
- `SessionService._build_feedback...` (≈ l.513–600) wraps this with a citation suggestion (`coach_source_suggestion`) and sets `speaker="coach"` on the advice bubble only.

### 1.5 ARP / trainer dashboards and n<10 suppression
- ARP: `web/arp.py` (`GET /arp`, observation and answer POSTs) over `reports/arp_digest.py::build_arp_digest` (per-teacher rows, rubric dots, escalated questions; consent-filtered).
- Trainer: `web/trainer.py` (`GET /trainer`, `/export.csv`) over `reports/trainer_aggregates.py::build_trainer_report`, plus `reports/class_struggles.py`, `teaching_skills.py`, `module_progress.py`. All aggregate cards use `settings.AGGREGATION_SUPPRESSION_N` (=10, `config.py:298`): below it the card shows `auth.access.SUPPRESSION_MESSAGE` and **not even counts**. Only teachers with `consent_share_scores=True` are counted; scope is district (trainer) or cluster (ARP).
- Rule for any new aggregate: count consenting teachers in scope; if `n < AGGREGATION_SUPPRESSION_N` return a suppressed object with no rows (copy `class_struggle_summary`).

### 1.6 Alembic
`backend/app/db/migrations/versions/` has 11 revisions. Chain starts at `6a7a8609f2ce` (initial). `alembic heads` (run this session) reports a single head, `c4e6a8b0d2f3` (add teacher start_seen_at); a new migration sets `down_revision = "c4e6a8b0d2f3"`. `make db-migrate` applies; tests run against a fresh DB via `scripts/pytest_fresh_db.py`.

### 1.7 Demo seeding and reset
- `db/seed.py::seed_database()` loads content + users/teachers/ARP/trainer/coach and `db/demo_data.py::populate_demo_cohort` (synthetic cohort). Fixed UUIDs make it idempotent. Demo teachers: `teacher.demo1` (NEW), `demo2` (READY, mid-week), `demo3` (READY, 3 completed moves, LEARN step), shared by judges.
- Reset: `reset_demo_teacher` / `reset_demo_teacher_unless_fresh` (`seed.py:438/461`) restore profile fields (`_DEMO_TEACHER_PROFILE`, `_DEMO_CLASS_STRUGGLES`, `_DEMO_TEACHING_SKILLS`, `_DEMO3_COMPLETED_MOVES`) and re-seed scene/session rows; called from `auth/router.py::_reset_demo_teacher` on login and logout, committed before the redirect (commit `69a05d1`). Anything a new feature stores on a demo teacher must be added to the reset or it will leak between judges.
- `DEMO_MODE` (`config.py:326`, default **True**) already gates demo-only UI (`web/teacher.py`, `web/chat_api.py`, `web/demo_samples.py`, `auth/router.py`).

### 1.8 How demo2 / demo3 reach their scenes
- demo2: `_seed_demo2_session_state` writes `session_state` = REHEARSE (attempt 1) with `_demo2_context()` (move `NUM_SUB_REGROUP_BUNDLES`, child ravi, a diagnosis); `_seed_demo2_one_on_one` inserts a `Scene` (`DEMO2_SCENE_ID`) after one teacher turn, computed with the real rule engine, plus the chat messages. The judge opens chat already inside the Ravi scene.
- demo3: `_seed_demo3_learn_step` inserts the LEARN message (catalog text + 2 buttons, no retrieval), `_seed_demo3_modules` seeds module progress; demo3 has struggles `LIT_MATRA_DROP`, `NUM_ADD_CARRY` and skill `asks_to_explain`, so its learn step is the matra move.

## 2. Settings flags (pattern)
`config.py` is the only home for tunables. Proposed pattern for v2 flags: `V2_<NAME>: bool = False` plus one helper `v2_enabled(flag) -> bool` = `flag or settings.DEMO_MODE`. Caveat: `DEMO_MODE` defaults to True, so "off by default otherwise" holds only where deployment sets `DEMO_MODE=false` (assumed for production; I did not read `render.yaml`/Render settings and must not change them). Names are fixed in the run that implements each feature.

## 3. Where each v2 feature hooks in

| Feature | Hooks into | Files touched (expected) | Notes / risks |
|---|---|---|---|
| **Class check-in** (closed-list, no free text, no child data) | New sub-flow like `skills_flow`; stage on `SessionContext`; `next_action.py` branch + `hint_*` key; buttons ≤3 so use number/chip replies | `class_profile/checkin_flow.py` (new), `sessions/service.py` (one dispatch block near l.876), `sessions/state_machine.py` (context field), `web/next_action.py`, `content/messages_{hi,en}.yaml`, `config.py`, new alembic revision + `db/models.py` (counts only), `reports/` + `web/trainer.py`/`arp.py` (aggregate card, n<10), `db/seed.py` reset | Persist ids from a closed list only. |
| **Child strip** (per-class summary row, no names) | Chat view header / teacher class page, server-rendered | `web/class_page.py`, `web/templates/*`, `app.css`, catalog | Avoid `chat.js` changes (payload; no raw Devanagari in JS). No child-level data stored. |
| **Level sorter** (class split by level, counts only) | Same sub-flow pattern; maps to struggles/moves via `class_struggles.yaml` `move_id` | `class_profile/` (new module), `service.py`, catalog, `reports/` aggregate | For the 8 struggles without `move_id`, show the cited tip and an honest "no practice move yet" line + handbook-question button. |
| **Talk-move feedback** | `coach.py` + move YAML `rubric`/`feedback_bank`; scoring already tags teacher acts | `llm/roles/coach.py` (fallback path), `content/moves/*.yaml` data, catalog; **not** rule engine or guards | Only reuses existing rubric criteria; no new claims. |
| **National / state labels** | Chunk `source_id`/`source_short_hi` already identify each source; label = metadata lookup | `content/` source metadata (data), `llm/roles/guide_answerer.py::format_guide_citation` or catalog, `web/templates` | Labels only from stored source metadata; no invented codes or page numbers. |
| **Cluster pack** (ARP-facing printable/summary) | `reports/arp_digest.py` data → new view | `web/arp.py`, `web/templates`, `reports/` (new builder), catalog | Consent-filtered, n<10 suppressed; no child or teacher free text. |

## 4. Constraints carried into every feature
- No change to the rule engine, the guards, login/auth, or composer layout rules. A feature that would need one is skipped and recorded BLOCKED.
- Payload baseline (this session, `python scripts/check_first_load.py`): teacher chat first load **127.63 KB raw / 30.49 KB gzip**; all offline assets **148.28 KB raw** vs the 150 KB limit (≈1.7 KB headroom on the offline-assets measure). Prefer server-driven buttons; client changes are the scarce resource.
- Tests go through the real `SessionService` with mocks (`backend/tests/unit/test_one_on_one_flow.py::Harness` is the reusable fixture), Hindi and English, flag on and off.

## 5. National core and state packs (built in run E2)

Every official source in `content/sources/sources.yaml` carries a scope: `scope: national` (NCERT Vidya Pravesh, NIPUN Bharat guidelines, NISHTHA FLN) or `scope: state` with `state: UP` (the two UP Samagra Shiksha handbooks). The scope is metadata only:

- **Citation text.** `format_guide_citation` (`llm/roles/guide_answerer.py`) looks the source up by its short Hindi name through `retrieval/source_scope.py` and adds the label from the catalog beside the page: `स्रोत: विद्या प्रवेश (NCERT), पृष्ठ 12 (राष्ट्रीय)` or `... (राज्य: उ.प्र.)`. Catalog keys: `ask_source_scope_national` and `ask_source_scope_state_<CODE>` in `messages_hi.yaml` (the one used; citation lines are Hindi in every UI language) and `messages_en.yaml` (kept for a future English line). A source with no scope (the Abhyas move summaries) is cited as before.
- **Retrieval tie-break.** In `retrieval/search.py` the result sort key is `(normalised score, raw BM25 score, national_rank)`, so a national source wins only when the two scores are exactly equal. A higher-scoring state chunk still ranks first. Tested in `backend/tests/unit/test_source_scope.py`.

### Adding a new state pack (for example Bihar)

1. Put the handbook PDF in `content/sources/` (PDFs are not committed; check the licence note).
2. Add an entry to `content/sources/sources.yaml`: `id`, `title`, `short_hi`, `file`, `sha256`, `as_of_date`, `lang`, `ingest: true`, and the scope fields `scope: state` and `state: BR`. For a font that has no usable text layer add `ocr: true` and `ingest_note` as the UP entries do.
3. Add two catalog lines (Hindi and English): `ask_source_scope_state_BR` with the label (for example "राज्य: बिहार" / "State: Bihar").
4. Ingest: `make content-ingest` (runs `python -m backend.app.retrieval.source_chunks`; the PDF path `python -m backend.app.retrieval.ingest --source <id>` takes one source). Check which of the two produced the chunks of the existing sources in `content/sources/README.md` before choosing. The result is `content/chunks/<id>.jsonl`. Nothing else in the code changes: retrieval reads every `*.jsonl` in that folder and the manifest gives the label.
5. Run `python -m pytest backend/tests/unit/test_source_scope.py backend/tests/unit/test_checkin_content_integrity.py`. The first fails if a source in the manifest has no scope or no catalog label; the content tests fail if a struggle or level cites a chunk that is not stored.
6. Only after that, map state-specific activities to the new chunks (`content/class_struggles.yaml`, `content/level_sorter.yaml`). A new pack never changes an existing citation by itself.

No document was ingested in this build.
