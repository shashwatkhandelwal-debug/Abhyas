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
- [ ] T20 Onboarding
- [ ] T21 Weekly loop + evidence
- [ ] T22 Intents, ASK, retrieval
- [ ] T23 Move path
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
