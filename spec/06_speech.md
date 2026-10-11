# 06 — Speech (STT, TTS, audio)

## 6.1 Audio pipeline (`speech/audio.py`)

All conversions via `ffmpeg` subprocess, stdin/stdout pipes. If a temp file is unavoidable, use `tempfile` under `/dev/shm` and delete in `finally`. **Never persist teacher audio.**

| Function | ffmpeg | Use |
|---|---|---|
| `to_wav16k(bytes, mime) -> bytes` | `-i pipe:0 -ac 1 -ar 16000 -f wav pipe:1` | STT input (from OGG/Opus WhatsApp, WebM/Opus or MP4/AAC browser) |
| `duration_s(bytes) -> float` | `ffprobe` | enforce limits |
| `split_for_stt(wav, max_s=25) -> list[bytes]` | `silencedetect=noise=-35dB:d=0.4` then cut at the silence nearest ≤ 25 s; hard cut if none | Sarvam REST is for clips < 30 s; explain-back is up to 60 s |
| `to_ogg_opus(wav) -> bytes` | `-c:a libopus -b:a 24k -ac 1 -ar 48000 -application voip -f ogg` | WhatsApp voice reply (WhatsApp requires OGG with Opus codec, mono) |
| `to_web(wav) -> bytes` | same OGG/Opus; plus `to_mp3(wav)` (`-b:a 32k`) fallback for Safari/iOS | web chat playback |
| `pitch_shift(wav, factor) -> wav` | `-af asetrate=22050*{f},aresample=22050,atempo={1/f}` | child voices |

Limits (config): `MAX_INBOUND_AUDIO_S = 90`, `EXPLAIN_BACK_MAX_SECONDS = 60` (soft: transcribe up to 90 s, tell her next time keep it to 1 min), `REHEARSE_TURN_MAX_S = 30`. Reject > 90 s with message `audio_too_long`.

## 6.2 STT (`speech/stt.py`)

```python
class Transcript(BaseModel): text: str; confidence: float; language: str | None; provider: str; ms: int
class STTProvider(Protocol):
    async def transcribe(self, wav16k: bytes, lang: str = "hi-IN", keyterms: list[str] = []) -> Transcript: ...
```

Providers (select by `STT_PROVIDER`):

1. **`sarvam`** (default for hosted demo). `POST https://api.sarvam.ai/speech-to-text`, header `api-subscription-key: $SARVAM_API_KEY`, multipart: `file` (wav), `model` = `$SARVAM_STT_MODEL` (default `saaras:v4`), `language_code=hi-IN`, `keyterms` = JSON array (≤ 50): persona names (रवि, प्रिया, अमन), move vocabulary (बंडल, तीली, हासिल, दहाई, इकाई, मात्रा, अक्षर), and the current item's numbers as Hindi words. Response `transcript`. Confidence: Sarvam returns `language_probability` only when auto-detecting; set `confidence = 0.9` when transcript non-empty and contains ≥ 1 Devanagari/Latin word, else 0.0. For split clips: call in parallel (`asyncio.gather`), join with space.
   **Verify the current API reference at https://docs.sarvam.ai before coding** (field names and model ids change). Keep all provider-specific strings in this one module.
2. **`bhashini`** (roadmap / optional): ULCA pipeline API (ASR `hi`). Implement only if a key is available (HUMAN INPUT); stub raising `ProviderNotConfigured` otherwise.
3. **`google`** (optional): Cloud Speech-to-Text v2 `hi-IN`. Stub unless key.
4. **`mock`**: returns the `text` stored alongside test audio fixtures (`tests/fixtures/audio/*.json`), or, for unknown audio, `MOCK_STT_TEXT` env (default the Ravi turn "रवि, 52 में से 17 कैसे घटाया? बताओ।"). The **web channel in mock mode also offers a text box** so evaluators/devs can type what they "said".

Error handling: timeout `STT_TIMEOUT_S = 8` per clip; one retry; then `STTUnavailable` → state unchanged, message `stt_failed`.
Low confidence (`< STT_MIN_CONFIDENCE`, 0.5) or < 2 words → confirm flow (08).
Text normalisation of transcripts: NFC, collapse whitespace; keep original numerals.

## 6.3 TTS (`speech/tts.py`, `speech/voices.py`)

```python
class TTSProvider(Protocol):
    async def synthesize(self, text_hi: str, voice: VoiceSpec) -> bytes: ...   # returns WAV 22.05 kHz mono
class VoiceSpec(BaseModel): provider_speaker: str; model: str; pace: float = 1.0; pitch_factor: float = 1.0
```

**Voices** (`content/voices.yaml`, loaded at startup; provider speaker ids are config, verify against Sarvam docs):

| voice id | Role | Sarvam model / speaker (default) | pace | pitch_factor (ffmpeg) |
|---|---|---|---|---|
| `abhyas` | system narrator / learn scripts | `bulbul:v3` / `ritu` | 0.95 | 1.0 |
| `coach` | feedback | `bulbul:v3` / `neha` | 0.95 | 1.0 |
| `model_teacher` | model rehearsal teacher | `bulbul:v3` / `pooja` | 1.0 | 1.0 |
| `child_ravi` | confident boy | `bulbul:v3` / `aayan` | 1.15 | 1.22 |
| `child_priya` | shy girl | `bulbul:v3` / `suhani` | 0.9 | 1.18 |
| `child_aman` | distracted boy | `bulbul:v3` / `soham` | 1.05 | 1.25 |

Pick final speakers by ear in task T15 (Vedant): generate the same line in 6–8 candidate speakers, choose 3 clearly distinct child-like voices, record choice in `PROGRESS.md`.

Provider `sarvam`: `POST https://api.sarvam.ai/text-to-speech`, header `api-subscription-key`, JSON `{text, language_code: "hi-IN", model, speaker, pace, speech_sample_rate: 22050}`; response `audios[0]` base64 WAV. Text limit: chunk at sentence boundaries if > 1500 chars (learn scripts) and concatenate WAVs with ffmpeg `concat`.
Numbers: before TTS, convert Arabic digits in child lines to Hindi number words (`hindi_numbers.to_words`) so "45" is spoken "पैंतालीस", not "four five".
Provider `mock`: returns a short silent/beep WAV whose length ∝ text length (so latency and players work).

**Cache** (`speech/cache.py`): key = sha256(voice_id + provider_speaker + model + pace + pitch + NFC text). Store final OGG and MP3 in `tts_cache`. Pre-warm at startup / on content publish: all learn scripts, model rehearsal lines, every message in `messages_hi.yaml` that has `audio: true`, and child template fallback lines for the seed items.

**Pre-recorded audio** (preferred over TTS for fixed prompts, HUMAN INPUT optional): if `content/audio/<key>.ogg` exists for a message key or learn script, use it instead of TTS. Name: `learn_<move_id>.ogg`, `msg_<message_key>.ogg`.

## 6.4 Latency instrumentation

Wrap each stage with a timer; store `turn.stage_ms` = `{download, convert, stt, tagger, engine, voice, guard, tts, upload, send}` and `latency_ms` = inbound received → last outbound sent. Expose p50/p95 on the admin page and via `eval/latency/benchmark_latency.py`.

Optimisations to implement:
- send the child's **text line immediately** on the web channel (before TTS) — perceived latency.
- run TTS for the child line and the template audio for "next" buttons in parallel.
- warm the Anthropic client and HTTP connection pools at startup (`httpx.AsyncClient` with keep-alive).
- prompt caching on act_tagger and child_voice system prompts.
