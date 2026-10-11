# 11 — Testing and evaluation

## 11.1 Automated tests (`make test`, CI on every push)

| Suite | Location | Must cover |
|---|---|---|
| Rule engine | `tests/unit/test_rule_engine.py`, `test_bugs.py`, `test_akshar.py` | 04 §4.5 (all 14 items) |
| Guards | `tests/unit/test_guards.py`, `test_hindi_numbers.py` | every guard: ≥ 3 pass + ≥ 3 fail fixtures; numbers 0–100 in words |
| LLM roles | `tests/unit/test_roles_*.py` | validate → guard → retry → fallback path, using MockLLM returning bad then good / bad then bad |
| State machine | `tests/unit/test_state_machine.py` | 08 §8.8 |
| Channels | `tests/integration/test_whatsapp_webhook.py` | verify GET challenge; bad signature 401; good signature 200 + background processing; dedupe; text/audio/button parsing (fixtures of real Meta payload shapes); outbound payload shapes; 24-h window/template choice |
| Web API | `tests/integration/test_web_chat.py` | text/audio/button send, idempotent retry with same client_msg_id, polling returns replies, auth required |
| Access control | `tests/integration/test_access.py` | 03 §3.3 |
| Reports | `tests/integration/test_reports.py` | n<10 suppression (exactly 9 → suppressed, 10 → shown); ARP digest excludes non-consenting scores; trainer pages contain no teacher names (grep rendered HTML for demo names) |
| Privacy | `tests/integration/test_privacy.py` | no inbound audio bytes reach DB (spy on session.add for bytes in non-tts tables); delete-my-data purges; consent withdrawal hides from ARP |
| Speech | `tests/unit/test_audio.py` | ffmpeg conversions on fixture OGG/WebM/MP4; split_for_stt on a 60 s fixture → chunks ≤ 25 s |
| Retrieval | `tests/integration/test_retrieval.py` | 10.4 |
| E2E | `tests/e2e/test_full_week.py` | NEW → DONE on web channel with mocks; same via WhatsApp webhook payloads with mocked Graph API (respx) |
| Content | `make content-validate` | 10.3 |

Coverage gate: `rule_engine/` 100% lines, `llm/guards.py` ≥ 95%, overall ≥ 80%.
Test DB: docker Postgres in CI (`services: postgres: image pgvector/pgvector:pg16`); each test in a transaction rolled back.

## 11.2 Live tests (`make test-live`, not in CI)

Skipped unless keys present. Real Claude on golden inputs (guard pass ≥ 90%), Sarvam STT on the 5 sample audios (word overlap with reference text ≥ 70%), Sarvam TTS returns playable audio, WhatsApp send to the team's test recipient.

## 11.3 Latency (`eval/latency/benchmark_latency.py` → `eval/latency/REPORT.md`)

- Drives the **hosted** deploy via the web API with the 5 sample audio files, 20 rehearsal turns each, concurrency 1 and 3.
- Reports p50/p95/max end-to-end and per stage (from `turn.stage_ms`), guard fallback rate, and a pass/fail vs 20 s.
- Also report on-device data cost: bytes uploaded/downloaded per full weekly loop (measure via API responses) — target < 2 MB normal, < 300 KB lite mode.

## 11.4 Coach calibration (`eval/calibration/`)

- `export_scenes.py`: exports N rehearsal transcripts (pilot + team role-plays) as anonymised JSONL.
- Coaches label blind in `/review/calibrate` (9.5); `make eval-kappa` computes per criterion: **quadratic-weighted Cohen's kappa** (sklearn `cohen_kappa_score(weights="quadratic")`) AI vs each coach and coach vs coach, with bootstrap 95% CI, plus exact-agreement %. Same for explain-back point statuses (unweighted kappa over covered/partial/missing).
- Report `eval/calibration/REPORT.md`: n, kappas, confusion matrices, examples of disagreements, what we changed in the prompt as a result (versioned prompt diff). **Report honestly even if n is small or kappa < 0.7.**
- Target for 1 Nov: ≥ 20 double-coded rehearsals (team-generated role-plays + pilot). Target for finale: ≥ 50.

## 11.5 Realism (`eval/realism/`)

- In-product rating after each scene (1–5 list). `make eval-realism` → mean, distribution, n, by persona and by move; free-text comments from user testing.
- Blind realism check (optional, strong evidence): 10 short exchanges, 5 engine-driven and 5 from a plain "pretend to be a child" LLM prompt; teachers guess which feels like their classroom children and rate realism. Script `realism/blind_pairs.py` generates both sets; the plain-LLM baseline uses `claude-haiku-5-5` with a naive prompt. This directly evidences the core innovation claim.

## 11.6 User testing protocol (`eval/user_testing/`) — scored under "proof of testing and refinement"

Owner: field lead (Divyansh). Two rounds.

**Recruit:** 5–10 government primary teachers (Classes 1–3, Hindi-medium) via personal networks / an NGO / ARP; at least 2 in-person observations. Adults, informed consent (`consent_form_hi.md` — agent writes; covers: purpose, what is recorded (transcripts only, no audio kept), voluntary, withdraw anytime, anonymised use in hackathon submission). **No children involved.**

**Session (30–40 min):**
1. Onboard on own phone (WhatsApp or web link).
2. Complete one weekly loop for `NUM_SUB_REGROUP_BUNDLES` (or move of her class).
3. Think-aloud during rehearsal; observer notes confusions.
4. Exit questions (`exit_questions_hi.md`): realism 1–5 ("बच्चे असली कक्षा जैसे लगे?"), usefulness 1–5, would use weekly (yes/maybe/no), time taken, hardest step, one thing to change; 5-item SUS-lite in Hindi.
5. Log into `eval/user_testing/sessions.csv` (anonymised id, date, device, network, channel, completion, timings, ratings, top quotes) — **no names/phones in git**.

**Round 1** (by 24 Oct) → `round1_findings.md`: top 5 issues, severity, decision (fix / won't fix / roadmap).
**Fixes** (25–28 Oct) → each linked to a commit.
**Round 2** (by 29 Oct) → `round2_findings.md`, before/after table (completion rate, avg time, realism, confusions).
**Deck page "User inputs and testing"** is generated from these files (13).

## 11.7 Guardrail evaluation (for the "AI use & technical strength" slide)

`eval/guards/REPORT.md` (`make eval-guards`): over all logged turns — child_voice first-pass guard pass %, retry pass %, fallback %, top rejection reasons with examples (e.g. "LLM said 35 while Ravi is in misconception — blocked"); coach evidence-quote failures; guide answer escalation rate. Include 3 concrete blocked examples in the deck.
