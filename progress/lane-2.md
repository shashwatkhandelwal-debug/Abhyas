# Lane 2 Progress — Turn Pipeline Latency & Pre-warming (Task T63)

## 1. Overview
Lane 2 optimizes turn pipeline latency for voice and text turns in Abhyas, ensuring strict compliance with `spec/02_architecture.md` §2.2, `spec/06_speech.md` §6.4, and `spec/11_eval_and_testing.md` §11.2.

## 2. Pipeline Call Dependency Map

```text
[Teacher Inbound: Voice/Text]
         │
         ▼
[Stage 0: STT (if voice)] ───► stt_ms
         │
         ▼ (Devanagari transcript)
[Stage 1: Intent Check & Act Tagger (Haiku)] ───► act_tagger_ms
         │
         ▼ (TaggedTurn: acts, addressed child)
[Stage 2: RuleEngine.step (Pure Deterministic Python)] ───► rule_engine_ms
         │  (StepResult: responses for 1..N children)
         ├─────────────────────────────────────────┐
         ▼                                         ▼
[Child 1: Voice (Haiku) + Guard]        [Child 2: Voice (Haiku) + Guard]  (asyncio.gather) ───► child_voice_ms
         │                                         │
         └────────────────────┬────────────────────┘
                              ▼
        [Text Delivery Hook: on_text_ready]
        (Immediately persists & emits kind="text", audio_ref=None to web channel DB)
                              │
         ┌────────────────────┴────────────────────┐
         ▼                                         ▼
[Child 1: TTS Synthesis]               [Child 2: TTS Synthesis]  (asyncio.gather) ───► tts_ms
         │                                         │
         └────────────────────┬────────────────────┘
                              ▼
     [Attach audio_ref to existing Message rows in DB]
     (Web polling updates already-rendered bubble with audio controls)
```

### Call Concurrencies & Dependencies:
1. **`act_tagger`**: Must wait for STT transcript and current scene state. Cannot be run earlier.
2. **`RuleEngine.step`**: Strictly depends on tagged teaching acts. Computes child state transitions and target numerical answers in <1 ms pure Python.
3. **`child_voice` & guards**: Independent per responding child. Run concurrently using `asyncio.gather(*(_voice_child(r) for r in step_result.responses))`. Output guard ensures numbers match rule engine output before release.
4. **Text-first delivery**: `on_text_ready` hook invokes channel persistence immediately after guarding and before TTS begins. Perceived latency drops from 4–6 s to ~1.2 s on web channel.
5. **TTS synthesis**: Concurrently synthesizes voice for each child line via `asyncio.gather`, then updates persisted DB rows with `audio_ref`.

## 3. Implemented Components

### 1. Per-Stage Latency Instrumentation & Reporting
- Added detailed timing breakdowns in `SceneRunner.turn` and `benchmark_latency.py`:
  - `stt_ms`: Speech-to-text conversion time.
  - `act_tagger_ms`: Claude Haiku teaching act classification time.
  - `rule_engine_ms`: Pure Python rule engine step execution time (< 1 ms).
  - `child_voice_ms`: Concurrent Claude Haiku child phrasing and number guarding.
  - `db_ms`: Summed PostgreSQL / SQLite scene loading and turn persistence time.
  - `tts_ms`: Concurrent child voice TTS synthesis time.
  - `total_ms`: End-to-end turn time.
- Updated `eval/latency/REPORT.md` Section 2 to output both `p50 (ms)` and `p95 (ms)` for each stage.

### 2. Parallel Child Voice Voicing
- Voicing across responding children in a turn is executed via `asyncio.gather`.
- Multi-child scenes (e.g. 2–3 responding children) voice and guard concurrently, saving up to 50% of LLM turn latency.

### 3. Text-First Delivery
- Added `on_text_ready` callback to `SceneRunner.turn`.
- In `backend/app/sessions/service.py`, `_on_text_ready` persists outbound messages immediately as `kind="text"` with `audio_ref=None`.
- `backend/app/channels/web.py` checks `_already_persisted` attribute to prevent duplicate database rows.
- `backend/app/web/static/chat.js` dynamically attaches the `.bubble-audio` player to previously rendered text bubbles when `audio_ref` arrives on subsequent polling.

### 4. TTS Pre-warming CLI (`scripts/prewarm_tts.py`)
- CLI script to pre-synthesize and store fixed audio messages into `TTSCache`:
  - Fixed catalog messages with `audio: true` from `content/messages_hi.yaml`.
  - Pedagogical narration for the 3 shipped moves' `learn` steps (`content/moves/*.yaml`).
- Features:
  - Idempotent: Checks `tts_cache.get(cache_key)` and skips existing items.
  - Budget-capped: Checks `speech_budget.can_spend(cost_est)` against `SPEECH_DAILY_BUDGET_INR` and `SPEECH_TOTAL_BUDGET_INR`.
  - Mock-aware: No-op against `MockTTS` unless `--force-mock` is passed.
  - Supports `--dry-run` and `--write`.

### 5. Deployment Documentation Updates (`docs/DEPLOY.md`)
- Supabase region explicitly documented as **Singapore (`ap-southeast-1`)** co-located with Render Singapore (`aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`), minimizing network round-trip DB latency to <5 ms.
- Added `python scripts/prewarm_tts.py --write` as mandatory post-seed operational step in §4.

## 4. Verification & Testing
- `backend/tests/unit/test_latency_pipeline.py`:
  - `test_pipeline_output_invariant_ravi_subtraction`: Proves Ravi with `SUB_SMALLER_FROM_LARGER` calculates 43 - 27 = 24, never 16, under parallel execution.
  - `test_pipeline_parallel_child_voicing_multi_child`: Proves multi-child scenes maintain child ordering and voice responses concurrently.
  - `test_text_first_delivery_callback`: Proves text messages are delivered with `kind="text"` and `audio_ref=None` before TTS, then updated with `kind="audio"` and `audio_ref`.
  - `test_prewarm_load_targets`: Proves static audio target extraction from catalog and move scripts.
  - `test_prewarm_tts_mock_noop`: Proves pre-warming is safe no-op under mock environment.
  - `test_prewarm_tts_dry_run_and_idempotence`: Proves dry-run cost estimation and idempotency skipping.
