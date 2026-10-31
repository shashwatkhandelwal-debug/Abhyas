# Latency Benchmark Report (spec/11 §11.3, T41)

- **Date:** 2026-10-17 19:13:08 UTC
- **Benchmark Target:** Local Pipeline Simulation
- **LLM Provider (effective):** `mock (no ANTHROPIC_API_KEY)`
- **STT Provider (effective):** `mock (no SARVAM_API_KEY)`
- **TTS Provider (effective):** `mock (no SARVAM_API_KEY)`
- **Target:** Voice-in → voice-out latency p95 < 20.0 s (20000 ms) on hosted deployment
- **Status:** **NOT MEASURED (mock providers)** (Simulated turn execution: **17.52 s**)
- **Total Tested Rehearsal Turns:** 10 (10 completed) across 5 evaluator sample inputs

> [!NOTE]
> **Mock Mode Execution:** Effective providers are running in mock mode:
> - LLM: `mock (no ANTHROPIC_API_KEY)`
> - STT: `mock (no SARVAM_API_KEY)`
> - TTS: `mock (no SARVAM_API_KEY)`
> Latency and data costs cannot be meaningfully benchmarked against live targets using mock components. Live benchmarking against the hosted deployment with real API keys is scheduled for the pre-submission freeze (T41 re-run, 30 Oct).

---

## 1. End-to-End Latency by Concurrency

| Concurrency | Completed Turns | p50 Latency (s) | p95 Latency (s) | Max Latency (s) | Target Compliance (< 20s) |
|---|---|---|---|---|---|
| **Concurrency 1** | 5/5 completed | 16.59 s | 17.46 s | 17.46 s | **N/A (mock providers)** |
| **Concurrency 3** | 5/5 completed | 17.08 s | 17.52 s | 17.52 s | **N/A (mock providers)** |
| **Combined** | 10/10 completed | 16.85 s | **17.52 s** | 17.52 s | **N/A (mock providers)** |

---

## 2. Per-Stage Latency Breakdown (`turn.stage_ms`)

| Stage | Description | p50 (ms) | p95 (ms) | Mean (ms) | % of Total Time |
|---|---|---|---|---|---|
| `download` | Ingest and receive inbound audio | 15.1 ms | 425.0 ms | 96.2 ms | 0.6% |
| `convert` | ffmpeg conversion to 16 kHz mono WAV | 270.5 ms | 933.9 ms | 411.1 ms | 2.4% |
| `stt` | Speech-to-text recognition | 0.9 ms | 16.2 ms | 2.6 ms | 0.0% |
| `tagger` | Teaching act tagging (Claude / Mock via tag_act) | 8174.4 ms | 8309.1 ms | 8185.6 ms | 48.4% |
| `engine` | Deterministic rule engine transition | 0.3 ms | 0.7 ms | 0.4 ms | 0.0% |
| `voice` | Child dialogue line selection (Claude / Mock via voice_child_line) | 8162.0 ms | 8579.8 ms | 8195.7 ms | 48.4% |
| `db` | Database persistence & queries summed | 10.5 ms | 15.1 ms | 9.0 ms | 0.1% |
| `guard` | Output schema & safety guards validation | 4.5 ms | 5.9 ms | 4.6 ms | 0.0% |
| `tts` | Text-to-speech voice synthesis | 0.7 ms | 12.6 ms | 1.9 ms | 0.0% |
| `send` | Outbound message delivery & dispatch | 6.6 ms | 23.9 ms | 9.1 ms | 0.1% |
| `total` | Total turn latency | 16848.2 ms | 17523.5 ms | 16916.2 ms | 100.0% |

---

## 3. Reliability & Guard Fallback Statistics

- **Total Evaluated Turns:** 10
- **Completed Turns:** 10 / 10
- **Failed / Timed-out Turns:** 0
- **Guard Fallback Count:** 0
- **Guard Fallback Rate:** **0.00%** (Target: < 5%)
- **Deterministic AI Children:** 100% adherence to rule engine state machine.

---

## 4. On-Device Low-Network Data Transfer Budget

Evaluated for a complete weekly learning cycle (LEARN → EXPLAIN_BACK → MODEL → REHEARSE → FEEDBACK → RETRY → REFLECT):

| Mode | Measured Data Transfer | Spec Target | Compliance |
|---|---|---|---|
| **Normal Mode** (auto audio preload) | **7.6 KB** (estimate on mock payloads) | < 2.0 MB | **N/A (estimate on mock payloads)** |
| **Lite Mode** (audio on tap only) | **8.8 KB** (estimate on mock payloads) | < 300 KB | **N/A (estimate on mock payloads)** |

---

## 5. Architectural Latency Optimisations Implemented in Code

1. **Deterministic Rule Engine:** Child responses and bug state transitions are computed deterministically in pure Python in < 5 ms, avoiding slow recursive LLM generation loops ([`backend/app/rule_engine/engine.py`](../../backend/app/rule_engine/engine.py)).
2. **Anthropic Prompt Caching:** Ephemeral prompt caching (`cache_control: {"type": "ephemeral"}`) is applied to static role instructions and schemas, reducing Claude API roundtrip token latency ([`backend/app/llm/client.py#L445`](../../backend/app/llm/client.py#L445)).
3. **HTTP Connection Pooling:** A shared singleton `httpx.AsyncClient` with keep-alive connection pooling (`limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)`) eliminates per-turn TLS handshake overhead ([`backend/app/speech/client.py#L16-L25`](../../backend/app/speech/client.py#L16-L25)).
4. **Static TTS Pre-warming:** Static message catalog prompts and fixed instructional lines are pre-warmed directly into the audio cache to eliminate runtime voice synthesis latency ([`backend/app/speech/spend.py#L182-L245`](../../backend/app/speech/spend.py#L182-L245)).
