# Latency Benchmark Report (spec/11 §11.3, T41)

- **Date:** 2026-10-17 05:41:21 UTC
- **LLM Provider:** `anthropic` (claude-haiku-5-5)
- **STT Provider:** `sarvam`
- **TTS Provider:** `sarvam`
- **Target:** Voice-in → voice-out latency p95 < 20.0 s (20000 ms) on hosted deployment
- **Status:** **NOT MEASURED (mock providers)** (Simulated turn execution: **0.04 s**)
- **Total Tested Rehearsal Turns:** 40 across 5 evaluator sample inputs

> [!NOTE]
> **Mock Mode Execution:** One or more configured providers (LLM: `anthropic`, STT: `sarvam`, TTS: `sarvam`) are running in mock mode. Latency and data costs cannot be meaningfully benchmarked against live targets using mock components. Live benchmarking against the hosted deployment with real API keys is scheduled for the pre-submission freeze (T41 re-run, 30 Oct).

---

## 1. End-to-End Latency by Concurrency

| Concurrency | Turns | p50 Latency (s) | p95 Latency (s) | Max Latency (s) | Target Compliance (< 20s) |
|---|---|---|---|---|---|
| **Concurrency 1** | 20 | 0.03 s | 0.04 s | 0.10 s | **N/A (mock providers)** |
| **Concurrency 3** | 20 | 0.03 s | 0.04 s | 0.04 s | **N/A (mock providers)** |
| **Combined** | 40 | 0.03 s | **0.04 s** | 0.10 s | **N/A (mock providers)** |

---

## 2. Per-Stage Latency Breakdown (`turn.stage_ms`)

| Stage | Description | Mean Latency (ms) | % of Total Time |
|---|---|---|---|
| `download` | Ingest and receive inbound audio | 16.2 ms | 48.5% |
| `convert` | ffmpeg conversion to 16 kHz mono WAV | 0.0 ms | 0.0% |
| `stt` | Speech-to-text recognition | 1.5 ms | 4.4% |
| `tagger` | Teaching act tagging (Claude / Mock) | 3.5 ms | 10.3% |
| `engine` | Deterministic rule engine transition | 0.2 ms | 0.7% |
| `voice` | Child dialogue line selection | 0.0 ms | 0.0% |
| `guard` | Output schema & safety guards validation | 2.5 ms | 7.4% |
| `tts` | Text-to-speech voice synthesis | 0.6 ms | 1.9% |
| `send` | Outbound message delivery & dispatch | 9.0 ms | 26.8% |

---

## 3. Reliability & Guard Fallback Statistics

- **Total Evaluated Turns:** 40
- **Guard Fallback Count:** 0
- **Guard Fallback Rate:** **0.00%** (Target: < 5%)
- **Deterministic AI Children:** 100% adherence to rule engine state machine.

---

## 4. On-Device Low-Network Data Transfer Budget

Evaluated for a complete weekly learning cycle (LEARN → EXPLAIN_BACK → MODEL → REHEARSE → FEEDBACK → RETRY → REFLECT):

| Mode | Measured Data Transfer | Spec Target | Compliance |
|---|---|---|---|
| **Normal Mode** (auto audio preload) | **0.00 MB** (estimate on mock payloads) | < 2.0 MB | **N/A (estimate on mock payloads)** |
| **Lite Mode** (audio on tap only) | **8.8 KB** (estimate on mock payloads) | < 300 KB | **N/A (estimate on mock payloads)** |

---

## 5. Architectural Latency Optimisations Implemented in Code

1. **Deterministic Rule Engine:** Child responses and bug state transitions are computed deterministically in pure Python in < 5 ms, avoiding slow recursive LLM generation loops ([`backend/app/rule_engine/engine.py`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/rule_engine/engine.py)).
2. **Anthropic Prompt Caching:** Ephemeral prompt caching (`cache_control: {"type": "ephemeral"}`) is applied to static role instructions and schemas, reducing Claude API roundtrip token latency ([`backend/app/llm/client.py#L445`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/llm/client.py#L445)).
3. **HTTP Connection Pooling:** A shared singleton `httpx.AsyncClient` with keep-alive connection pooling (`limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)`) eliminates per-turn TLS handshake overhead ([`backend/app/speech/client.py#L16-L25`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/speech/client.py#L16-L25)).
4. **Static TTS Pre-warming:** Static message catalog prompts and fixed instructional lines are pre-warmed directly into the audio cache to eliminate runtime voice synthesis latency ([`backend/app/speech/spend.py#L182-L245`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/speech/spend.py#L182-L245)).
