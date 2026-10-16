# Lane B Progress (Pipeline: LLM client, Speech, Rehearsal, Sessions, Retrieval, Scoring, Jobs)

Branch: `lane-b`
Worktree: `C:\Users\ASUS\Downloads\abhyas-lane-b`
Port: 8002
Database: `abhyas_b` (waits for Docker Desktop)

## Tasks
- [x] T08 LLM client + MockLLM
- [x] T15 Audio utils
- [x] T16 STT
- [x] T17 TTS + voices
- [x] T18 Core service skeleton
- [x] T19 SceneRunner
- [x] T20 Onboarding
- [x] T21 Weekly loop + evidence
- [x] T22 Intents, ASK, retrieval
- [x] T23 Move path
- [ ] T24 Scheduler & jobs

## Checkpoints
- After T17 (stop and report) - Completed
- After T19 (stop and report before T20) - Reached
- After T21 (stop and report)
- Every 3 tasks otherwise

## Deviations from spec
None.

## Self-Reviews
- Review fixes: Replaced blocking subprocess with async subprocess exec, implemented shared Anthropic and Speech HTTP client singletons, removed deprecated temperature extra_body.
- Cost control: Added speech budget tracker (daily & total caps), STT 15s increment pricing, TTS character pricing, lite-mode fallback, cache hits with zero spend, pre-warming helper, and Bhashini ULCA pipeline adapter.
- T18: Implemented MessageCatalog loader with startup validation & gender variants, per-teacher asyncio locks, and ConversationService with graceful degradation.
- T19: Implemented SceneRunner orchestrating the 5-stage pipeline (stop keywords -> act_tagger -> RuleEngine -> child_voice guarded -> TTS -> persistence) with stage_ms timings and full multi-turn integration test running the Ravi worked example end-to-end.
- Review Items 1-11 (CHANGES 254f622):
  1. Speech spend & LLM token usage survive restarts via DB queries in IST (Asia/Kolkata); Bhashini cost tracked at 0.0 INR.
  2. Cap-hit fallback order: Sarvam cap reached -> Bhashini (if configured) -> lite mode; STT cap caught in ConversationService replying with stt_budget_type_please.
  3. TTS cache survives deploys via Postgres tts_audio table; local disk cache kept as fallback; prewarming via script/admin.
  4. TTS cache key single source of truth: synthesize() returns (wav_bytes, cache_key); VoiceSpec has gender: Literal['f', 'm']; Bhashini gender mapping direct.
  5. Scenes & turns persist to Postgres scene and turn tables; InMemorySceneStore retained behind SceneStore protocol.
  6. Intent matching in backend/app/core/intents.py per spec/08 §8.3 (NFC + lowercase, word-boundary whole/prefix match).
  7. Low-confidence confirmation: store pending transcript per teacher; 'हाँ' accepts, 'फिर से' discards; in REHEARSE skips confirm and flags turn low_conf.
  8. No hardcoded Hindi in conversation.py or scene_runner.py: catalog keys used for scene_all_correct, scene_ended_neutral, stt_failed, stt_confirm, stt_budget_type_please.
  9. Removed echo fallback in ConversationService: fails fast with RuntimeError if session_dispatcher is None in production.
  10. SceneRunner: concurrent child TTS with asyncio.gather, last 4 child lines in context, logs unknown acts, removed hardcoded 52-17 fallback.
  11. locks.py: ref-counted idle per-teacher lock pruning, single Render instance docstring note.
- Deliberate Practice & Repository Hardening (CHANGES 2f9f2de & followup):
  1. SessionRepository requires AsyncSession; removed all in-memory fallback dicts and swallowed exceptions; IntegrityError races handled via begin_nested() savepoints to avoid discarding outer transaction state.
  2. Deleted dead backend/app/sessions/manager.py and removed exports from backend/app/sessions/__init__.py.
  3. Broadened hygiene test in test_state_machine.py: zero bare except, zero except (Exception/BaseException), zero _in_memory substrings, zero Devanagari literals across backend/app/sessions/*.py.
  4. FakeSessionRepository in tests: uses cast(AsyncSession, session) without type: ignore.
  5. path.py notes: replaced hardcoded candidate table with deterministic path_score.rank_moves fed from loaded MoveCards; keeps induction fallback when content/induction_track.yaml is absent.
  6. Real Postgres repository integration tests added in backend/tests/integration/test_session_repository.py covering idempotency, forced IntegrityError race recovery, consent round-trip, and fresh process/session state continuity.
- T22 & T23 Implementation:
  1. Chunk seed pipeline: `backend/app/retrieval/ingest.py` generates `content/chunks/seed_from_moves.jsonl` from the 4 seed move YAMLs, extracting learn scripts and key points with normalized text, tags, and source metadata.
  2. BM25 Hindi retrieval: `backend/app/retrieval/search.py` implements `GuideRetriever` using `rank_bm25.BM25Okapi` with Unicode-aware whitespace/punctuation tokenization preserving matras, returning top-k scored `RetrievedChunk`s.
  3. ASK conversation flow: Wired into `SessionService.handle_inbound`, classifying questions via `classify_question`, handling clarifications, retrieving BM25 chunks, generating answers via `answer_guide_question`, creating `ReviewItem` for admin/escalated questions, and cleanly resuming prior state with state-specific prompt resumption.
  4. Move path ranking: `backend/app/sessions/path.py` wires `rank_moves` from `path_score.py` fed with loaded `MoveCard`s, preserving `DEFAULT_INDUCTION_ORDER` fallback when `content/induction_track.yaml` is absent and passing zero-broad-exception hygiene checks.
