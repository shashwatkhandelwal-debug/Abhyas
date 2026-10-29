# V2 progress (branch feat/v2-national, cut from main 62014e5, tag pre-v2-build)

## Run A (A1, A2)
- A1 DONE: docs/ux/V2_DESIGN.md (commit "V2-A1").
- A2 DONE: commit "V2-A2". Form of address already followed the choice for children (दीदी/मैडम for she, सर for he) in the template and LLM-prompt paths; gaps fixed: consent_details and hint_model got text_m, and the keyword act-tagger fallback now recognises the masculine "मैं करके दिखाता / बताता".
- Flags added: none.
- Payload (check_first_load.py, before and after; no client files changed): first load 127.63 KB raw / 30.49 KB gzip; offline assets 148.28 KB raw / 37.71 KB gzip (limit 150 KB).
- Full gate: NOT PASSED in this environment (see docs/ux/V2_RUN_A.md): local Postgres on :5433 has no pgvector extension and Docker is not running.
- Branch head after run A work: see V2_RUN_A.md / git log (docs commit follows 2c86716).
