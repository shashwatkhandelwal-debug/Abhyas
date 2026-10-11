# 15 — Human inputs (the agent must not invent these)

For each item: what is needed, who, by when, and what the agent does meanwhile. The agent lists open items under `PROGRESS.md › Blocked on humans` and keeps building against the fallback.

| # | Input | Owner (suggested) | Needed by | Agent fallback meanwhile |
|---|---|---|---|---|
| H1 | **Anthropic API key** from the hackathon's Claude credits (USD 500) | Shashwat | 14 Oct | MockLLM; live tests skipped |
| H2 | **Sarvam AI API key** (or chosen STT/TTS provider + key) | Vedant | 15 Oct | Mock STT/TTS; text box in web chat |
| H3 | **Choice of 3 child voices + narrator/coach/model-teacher voices** (listen to `eval/voices/` audition files) | Vedant | 18 Oct | defaults in 06 §6.3 |
| H4 | **Meta WhatsApp**: developer app, test number, phone number id, permanent token, app secret, verify token, 5 registered recipient numbers | Shashwat | 19 Oct | WhatsApp channel tested with mocked Graph API only |
| H5 | **WhatsApp template approval** — submit templates from `content/whatsapp_templates.yaml` (Utility, Hindi) | Shashwat | submit by 20 Oct | templates marked `approved: false`; outside-window sends skipped & logged |
| H6 | **Render account + Supabase project** (billing for Render Starter) | Shashwat | 17 Oct | local docker only |
| H7 | **Official source PDFs**: NIPUN Bharat guidelines; UP Shikshak Sandarshika (Ganit Class 2, Bhasha Class 1); NCERT Vidya Pravesh / FLN materials; hackathon resource list | Divyansh | 20 Oct | `seed_from_moves.jsonl` chunks; `module_ref.verified: false` |
| H8 | **FLN coach / education mentor review** of the 4 seed moves (key points, rubric, scenario realism, bug list "common in UP classrooms?") — book the hackathon **education mentor** session for this | Divyansh + team | 22 Oct | moves stay `in_review`; demo serves them with "समीक्षा में" label |
| H9 | **2 coaches (or 1 coach + 1 trained team member) for blind double-coding** ≥ 20 rehearsals | Divyansh | 29 Oct | kappa report states n and limitation |
| H10 | **5–10 teachers for user testing**, two rounds (by 24 Oct, by 29 Oct), with signed/recorded consent | Divyansh | 24 / 29 Oct | — (cannot be faked; report what happened) |
| H11 | Optional **pre-recorded learn scripts** in a real teacher's voice (`content/audio/learn_<move>.ogg`) | any | 25 Oct | TTS narrator |
| H12 | **Evaluator GitHub IDs** (from organisers) | Shashwat | 31 Oct | repo is public |
| H13 | **Demo passwords** for the submission form (rotate `DEMO_PASSWORD` on Render) | Shashwat | 31 Oct | dev default (never used in prod) |
| H14 | **Demo video** recording + YouTube upload; **deck** (PPTX) from `docs/deck_outline.md` | whole team | 31 Oct | agent supplies script, outline, screenshots, diagrams |
| H15 | **Sample voice notes** recorded by a Hindi-speaking teammate reading `eval/samples/samples.yaml` lines (more realistic than TTS for STT testing) | any | 22 Oct | TTS-rendered samples |
| H16 | Optional Voyage AI key (dense retrieval) | — | — | BM25 only |
| H17 | Decision: open-source licence MIT (default) — confirms the +USD 250 credits open-source bonus | team | 12 Oct | MIT |

Never commit: real phone numbers, teacher names, transcripts from real teachers, API keys, the `.env` file, signed consent forms.
