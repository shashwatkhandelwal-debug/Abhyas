# 03 — Data model

Postgres 15+ with `pgvector` and `pgcrypto`. Implement as SQLAlchemy 2 models + **one Alembic migration per task** that adds tables. Local dev uses docker compose Postgres (no SQLite).

## 3.1 Conventions

- PKs `uuid` default `gen_random_uuid()` unless stated. All timestamps `timestamptz` default `now()`.
- **No raw phone numbers stored.** `phone_hash = sha256(PHONE_HASH_SALT + E.164 number)`. The raw number is needed to *send* WhatsApp messages: store it **encrypted** in `teacher_contact.phone_enc` (Fernet, key `PHONE_ENC_KEY`) in a separate table that only the channel layer reads.
- **No audio stored**, ever. Transcripts only.
- Teacher-facing text stored NFC-normalised.
- Every LLM call logged in `llm_call` (no full prompt text for teacher content beyond the transcript already stored; store prompt version + token counts).

## 3.2 Schema (DDL — source of truth for the Alembic migrations)

```sql
create extension if not exists vector;
create extension if not exists pgcrypto;

-- ── Organisation ───────────────────────────────────────────────
create table batch (            -- a training batch (e.g. "Kanpur Nagar Oct-2026 NIPUN Ganit")
  id text primary key, name text not null, district text, block_id text, module text,
  created_at timestamptz default now());

create table cluster (id text primary key, name text not null, block_id text, district text);

create table app_user (          -- web logins: arp, trainer, coach, admin, and web teachers
  id uuid primary key default gen_random_uuid(),
  username text unique not null, password_hash text not null,
  role text not null check (role in ('teacher','arp','trainer','coach','admin')),
  display_name text, cluster_id text references cluster(id),   -- arp scope
  district text,                                                -- trainer scope
  teacher_id uuid,                                              -- set when role='teacher'
  is_demo boolean default false, created_at timestamptz default now());

create table teacher (
  id uuid primary key default gen_random_uuid(),
  phone_hash text unique,                    -- null for web-only demo teachers
  name text, school_id text, cluster_id text references cluster(id), block_id text, district text,
  batch_id text references batch(id),
  experience_band text check (experience_band in ('0-1','2-5','6-10','10+')),
  first_year boolean, classes int[],
  address_form text default 'f' check (address_form in ('f','m')),   -- grammatical gender for Hindi messages
  preferred_channel text default 'whatsapp' check (preferred_channel in ('whatsapp','web')),
  lite_mode boolean default false,           -- text-only replies
  consent_service boolean default false,     -- required to use the product
  consent_share_scores boolean default false,-- ARP may see individual scores
  consent_class_audio boolean default false, -- always false in this build
  consent_research boolean default false,    -- anonymised use in evaluation
  is_demo boolean default false,             -- synthetic, for ARP/trainer demo views
  onboarding_state text default 'NEW',
  last_inbound_at timestamptz, created_at timestamptz default now());

create table teacher_contact (
  teacher_id uuid primary key references teacher(id) on delete cascade,
  phone_enc bytea not null);

create table invite_code (code text primary key, cluster_id text references cluster(id), batch_id text references batch(id),
  district text, active boolean default true);

create table arp_assignment (arp_user_id uuid references app_user(id), cluster_id text references cluster(id),
  primary key (arp_user_id, cluster_id));

create table consent_log (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id),
  field text not null, value boolean not null, channel text, text_version text, created_at timestamptz default now());

-- ── Content (published releases) ───────────────────────────────
create table content_release (id text primary key, notes text, published_by uuid references app_user(id),
  published_at timestamptz default now(), is_active boolean default false);
create table move (id text not null, release_id text references content_release(id), domain text not null,
  title_hi text not null, sankul_month text, status text not null check (status in ('draft','in_review','approved')),
  payload jsonb not null, approvals jsonb default '[]', primary key (id, release_id));
create table persona (id text not null, release_id text references content_release(id), payload jsonb not null,
  primary key (id, release_id));
create table bug_rule (id text primary key, kind text check (kind in ('math','reading')), code_ref text not null,
  description_hi text, research_ref text);

-- ── Sessions ───────────────────────────────────────────────────
create table session_state (
  teacher_id uuid references teacher(id) on delete cascade,
  week_start date not null,                -- Monday of the ISO week, or a "demo week" counter date
  move_id text not null,
  state text not null,                     -- see 08 state list
  prior_state text,                        -- for ASK interrupt resume
  rehearse_attempts int default 0,
  context jsonb default '{}',              -- free per-state data (pending confirm, last buttons, etc.)
  updated_at timestamptz default now(),
  primary key (teacher_id, week_start));

create table move_path (teacher_id uuid references teacher(id) on delete cascade, position int,
  move_id text, reason text, primary key (teacher_id, position));

create table scene (               -- one rehearsal attempt
  id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  move_id text, week_start date, attempt int, mode text default 'normal' check (mode in ('normal','placement','sankul')),
  engine_state jsonb not null,     -- serialised SceneState (04)
  status text default 'active' check (status in ('active','ended')),
  end_reason text, teacher_turns int default 0, started_at timestamptz default now(), ended_at timestamptz);

create table turn (
  id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  scene_id uuid references scene(id) on delete cascade, idx int,
  role text not null,              -- 'teacher' | persona id | 'system'
  transcript text, stt_confidence real,
  acts text[], addressed_child text, problem jsonb,
  rule_result jsonb, line_hi text, guard_status text,   -- 'pass' | 'retry_pass' | 'fallback'
  latency_ms int, stage_ms jsonb,  -- {"stt":..,"tagger":..,"engine":..,"voice":..,"tts":..,"send":..}
  created_at timestamptz default now());

create table message (             -- every inbound/outbound message (web history + audit). No audio bytes.
  id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  direction text check (direction in ('in','out')), channel text, channel_msg_id text,
  kind text, text text, audio_ref text, buttons jsonb, speaker text, template_name text,
  state_at text, created_at timestamptz default now(),
  unique (channel, channel_msg_id));

-- ── Scores & evidence ──────────────────────────────────────────
create table rehearsal_score (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  scene_id uuid references scene(id), move_id text, attempt int,
  scores jsonb not null, evidence jsonb not null, strength_hi text, change_hi text, exact_words_hi text,
  confidence real, needs_review boolean default false, prompt_version text, model text,
  created_at timestamptz default now());

create table explain_score (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  move_id text, transcript text, points jsonb not null, misconceptions text[], confidence real,
  needs_review boolean default false, prompt_version text, model text, created_at timestamptz default now());

create table adoption_evidence (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  move_id text not null, level int not null check (level between 1 and 5),
  source text not null check (source in ('rehearsal','reflection','peer_checklist','arp_observation','child_check')),
  detail jsonb, created_by uuid, created_at timestamptz default now());

create table realism_rating (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  scene_id uuid references scene(id), rating int check (rating between 1 and 5), created_at timestamptz default now());

-- ── Ask any time ──────────────────────────────────────────────
create table question (id uuid primary key default gen_random_uuid(), teacher_id uuid references teacher(id) on delete cascade,
  text text not null, category text, clarifying_asked boolean default false,
  answer_hi text, source_ids text[], confidence real,
  status text not null check (status in ('answered','escalated','arp_answered','closed')),
  followup_at timestamptz, followup_result text, created_at timestamptz default now());

create table doc_chunk (id text primary key, source_id text not null, source_short_hi text, section text, page int,
  text text not null, tokens text[], embedding vector(1024), created_at timestamptz default now());
create index on doc_chunk using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- ── Review / ops ───────────────────────────────────────────────
create table review_item (id uuid primary key default gen_random_uuid(),
  kind text check (kind in ('rehearsal_score','explain_score','question','move','guard_failure')),
  ref_id text not null, reason text, status text default 'open' check (status in ('open','resolved')),
  resolution jsonb, resolved_by uuid, created_at timestamptz default now(), resolved_at timestamptz);

create table calibration_label (id uuid primary key default gen_random_uuid(), scene_id uuid references scene(id),
  explain_score_id uuid references explain_score(id), coach_user_id uuid references app_user(id),
  scores jsonb not null, note text, blind boolean default true, created_at timestamptz default now());

create table arp_observation (id uuid primary key default gen_random_uuid(), arp_user_id uuid references app_user(id),
  teacher_id uuid references teacher(id) on delete cascade, move_id text, checklist jsonb, notes text, observed_on date,
  created_at timestamptz default now());

create table scheduled_job (id uuid primary key default gen_random_uuid(), kind text not null, run_at timestamptz not null,
  payload jsonb, status text default 'pending' check (status in ('pending','done','failed','cancelled')),
  attempts int default 0, last_error text, created_at timestamptz default now());
create index on scheduled_job (status, run_at);

create table template_send (id uuid primary key default gen_random_uuid(), teacher_id uuid, template_name text,
  category text, est_cost_inr numeric(8,3), sent_at timestamptz default now());

create table llm_call (id uuid primary key default gen_random_uuid(), role text, prompt_version text, model text,
  input_tokens int, output_tokens int, cache_read_tokens int, latency_ms int, outcome text, -- ok|retry_ok|fallback|error
  created_at timestamptz default now());

create table tts_cache (key text primary key, voice text, text_hi text, mime text, bytes bytea, created_at timestamptz default now());
-- tts_cache holds SYNTHETIC audio only (our voices), never user audio.

-- ── Aggregates for trainer view (materialised by job) ──────────
create table agg_module_batch (batch_id text, move_id text, n_teachers int,
  explain_missing jsonb,       -- {kp_id: count}
  rubric_dist jsonb,           -- {criterion_id: {"0":n,"1":n,"2":n}}
  ladder_dist jsonb,           -- {"1":n,...,"5":n}
  active_rate real, computed_at timestamptz default now(), primary key (batch_id, move_id));
```

## 3.3 Access rules (enforce in the service layer AND test them; add Supabase RLS as defence in depth)

The app connects with a service role, so **authorisation is enforced in code** (`auth/guards.py` + query helpers). Every query that returns teacher-level data must go through a scoped helper:

| Role | Can read |
|---|---|
| teacher | own rows only |
| arp | teachers where `cluster_id ∈ own clusters`; **scores/transcripts only if `consent_share_scores = true`**; otherwise only: practised move (yes/no), asked-for-help flag, escalated questions (text only, no name if no consent → shown as "शिक्षक #<short hash>") |
| trainer | `agg_module_batch` rows only, filtered to own district; rows with `n_teachers < AGGREGATION_SUPPRESSION_N` rendered as "समूह छोटा है (n<10)" |
| coach | review_item, move drafts, anonymised transcripts attached to review items |
| admin | everything (demo/ops) |

Tests (in `tests/integration/test_access.py`): an ARP cannot fetch scores for a non-consenting teacher in own cluster; cannot fetch any teacher from another cluster; trainer endpoint never returns a group with n<10; no endpoint returns `teacher_contact`.

Supabase RLS (defence in depth): enable RLS on all tables; no anon policies (the app uses the service key server-side only). Document this in README.

## 3.4 Retention

- Audio: never persisted (assert in tests: no `bytes`/`bytea` column receives user audio; `tts_cache` writes only from TTS module).
- Transcripts: retained for the pilot; job `retention_purge` deletes `turn.transcript`, `message.text` for teachers who withdraw consent (within 24 h) and everything for teachers who send "मेरा डेटा हटाएँ" (delete-account flow, 08).

## 3.5 Seed data (`make db-seed`)

1. Content release `r2026.10-demo` from `content/moves/*.yaml` + `content/personas/*.yaml` (status as in file).
2. Bug rules registry rows from `rule_engine/bugs/registry.py`.
3. Doc chunks from `content/chunks/*.jsonl` (if present).
4. Demo users (passwords from env `DEMO_PASSWORD`, default `abhyas-demo-2026` in dev only):
   - `teacher.demo1`, `teacher.demo2`, `teacher.demo3` (role teacher; demo1 fresh/NEW, demo2 mid-week in REHEARSE, demo3 completed 3 moves)
   - `arp.demo` (cluster `KNP-C01`), `trainer.demo` (district Kanpur Nagar), `coach.demo`, `admin.demo`
5. **Synthetic demo cohort** (`db/demo_data.py`, `is_demo = true`, names prefixed "डेमो"): batches `KNP-B1` (25 teachers), `KNP-B2` (18), `KNP-B3` (8 — shows suppression); cluster `KNP-C01` has 12 of them, 7 consenting. Generate rehearsal/explain scores, evidence levels and questions with a fixed random seed so screenshots are reproducible. Every page showing demo data displays a banner "डेमो डेटा — वास्तविक शिक्षक नहीं".
