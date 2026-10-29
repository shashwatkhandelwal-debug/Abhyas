# V2 progress (branch feat/v2-national, cut from main 62014e5, tag pre-v2-build)

## Run A (A1, A2)
- A1 DONE: docs/ux/V2_DESIGN.md (commit "V2-A1").
- A2 DONE: commit "V2-A2". Form of address already followed the choice for children (दीदी/मैडम for she, सर for he) in the template and LLM-prompt paths; gaps fixed: consent_details and hint_model got text_m, and the keyword act-tagger fallback now recognises the masculine "मैं करके दिखाता / बताता".
- Flags added: none.
- Payload (check_first_load.py, before and after; no client files changed): first load 127.63 KB raw / 30.49 KB gzip; offline assets 148.28 KB raw / 37.71 KB gzip (limit 150 KB).
- Full gate: PASSED on rerun against the compose pgvector DB: 1751 passed, 1 skipped (see docs/ux/V2_RUN_A.md). The first attempt failed only because the :5433 server had no pgvector.
- Branch head after run A work: see V2_RUN_A.md / git log (docs commit follows 2c86716).

## Run B (B0, B1, B2)
- B0 DONE: commit "V2-B0" (neutral `speaker_model_teacher_neutral`, follows address_form; no client change).
- B1 DONE: commit "V2-B1" (after-class check-in; alembic `e9b1d3f5a7c2`, table `class_checkin`; button cap per message 3 to 5).
- B2 DONE: three Hindi transcripts in docs/ux/V2_RUN_B.md.
- Flags added: `CLASS_CHECKIN_ENABLED` (default False; on when `DEMO_MODE` is on, via `v2_enabled`).
- Payload (no client file changed): first load 127.70 KB raw / 30.50 KB gzip; offline assets 148.34 KB raw / 37.73 KB gzip (limit 150 KB).
- Full gate: result recorded in docs/ux/V2_RUN_B.md.
- Branch head: see `git log`.

