# 13 — Submission deliverables (Build stage, due 1 Nov 2026 23:59 IST)

Required by the organisers: (1) testable hosted link + any software needed, (2) source repo, (3) public YouTube demo video, judges watch only the first 3 minutes, (4) short PowerPoint deck. Tech-flow guidance adds: test credentials for every role, 3–5 sample inputs, what works offline/low network, 2–3 min fallback video, README with setup/run/.env.example, list of every external AI service and where keys are needed, no secrets, no real user data, no commits after deadline.

Build-stage scoring: Efficacy & user-centricity 35 · Effective AI use & technical strength 30 · Innovation 25 · Future roadmap 10.

## 13.1 README.md (agent writes; structure fixed)

1. **Abhyas — अभ्यास** one-line pitch + 30-second GIF of a rehearsal (record in T52).
2. **Try it** — hosted URL; **credentials table**:

| Role | Username | Password | What to try |
|---|---|---|---|
| Teacher (new) | teacher.demo1 | (in submission form) | onboarding → first weekly loop |
| Teacher (mid-week) | teacher.demo2 | … | jump straight into rehearsal with 3 children |
| Teacher (experienced) | teacher.demo3 | … | progress page, evidence ladder, ask a question |
| ARP | arp.demo | … | weekly digest, visit list, answer escalated question |
| Trainer (DIET) | trainer.demo | … | module × batch view, n<10 suppression (batch KNP-B3) |
| FLN coach | coach.demo | … | review queue, blind calibration, move approval |
| Admin | admin.demo | … | latency, guardrail stats, fast-forward timers, reset demo |
WhatsApp: number + join instructions (Meta test numbers only accept pre-registered recipients — evaluators who want WhatsApp send their number via the form; otherwise watch the video section).
3. **Sample inputs** (3–5) with what to expect — from `eval/samples/samples.yaml`; buttons for these exist in the chat in demo mode.
4. **How it works** — the layered diagram (02 §2.1) as an image + 6 bullets; the rule-engine principle in 3 sentences with the Ravi example.
5. **AI services used** table: Claude (`claude-haiku-5-5`: intent, act tagging, child voice; `claude-sonnet-5-5`: coach, fidelity, guide answers, content generation) — key `ANTHROPIC_API_KEY`; Sarvam AI STT/TTS — `SARVAM_API_KEY`; Meta WhatsApp Cloud API — `WHATSAPP_*`; optional Voyage embeddings — `VOYAGE_API_KEY`. State which run in mock mode without keys.
6. **Guardrails** — list with links to `llm/guards.py` and `eval/guards/REPORT.md`.
7. **Low connectivity & low-cost devices** table:

| Part | Needs network? | Degrades to |
|---|---|---|
| Learn summary, peer checklist, last 50 messages | No (cached PWA) | — |
| Sending a voice note / text | Queued offline, auto-sent when back | outbox with retry |
| Rehearsal replies | Yes (server AI) | text-first replies; lite mode = no audio download |
| Audio playback | On tap in lite mode | text always shown |
| WhatsApp channel | WhatsApp's own offline queue | text fallback on audio failure |
Data per weekly loop: measured X MB normal / Y KB lite (from latency report).
8. **Run locally** — prerequisites (Docker, Python 3.11, ffmpeg), `cp .env.example .env`, `make setup db-up db-migrate db-seed dev`, open `http://localhost:8000`; all providers mocked by default.
9. **Repository map**, **tests** (`make test`), **evaluation reports** links.
10. **Privacy** — DPDP-aligned summary (no audio stored, consent gates, n≥10, children never scored).
11. **Limitations (honest)** and **Roadmap** (13.4).
12. **Licence** MIT · Team Asymptotes · hackathon attribution.

## 13.2 Demo video (YouTube, public/unlisted-public, ≤ 3:00) — `docs/video_script.md`

| Time | Visual | Voice-over (English with Hindi on screen, or Hindi with English subtitles — team choice) |
|---|---|---|
| 0:00–0:15 | Teacher in a real classroom / B-roll; text "Trainings end. Practice doesn't happen." | Problem: FLN moves are taught in a training hall, never practised; trainers see attendance, not adoption. |
| 0:15–0:30 | Phone: WhatsApp chat opens, learn voice note | Abhyas: 15 minutes a week, voice, Hindi, on WhatsApp. |
| 0:30–1:30 | **Rehearsal** — board shows 43 − 27; Ravi says 24, Priya 26, Aman 20; teacher says "रवि, 43 में से 27 कैसे घटाया?"; Ravi: "3 में से 7 नहीं घटता, तो 7 में से 3 घटाया… 24!"; teacher uses bundles; Priya shy; teacher tells answer to Aman → Aman parrots then relapses on next problem | Children's mistakes are computed by a rule engine from research on children's errors; Claude only voices them; a guard blocks any line the engine didn't produce. Telling the answer doesn't work — just like a real class. |
| 1:30–1:55 | Feedback screen: strength / change / exact words with highlighted quote; retry improves | Evidence-cited feedback; retry. |
| 1:55–2:15 | Explain-back score + ask a question with cited guide + ARP escalation | |
| 2:15–2:35 | ARP digest (consenting only), trainer view with n<10 suppressed | Adoption, not attendance; privacy by design. |
| 2:35–2:50 | User testing: photos (with consent, no children), 2 quotes, before/after numbers | Tested with N teachers, what we changed. |
| 2:50–3:00 | Lite mode on a cheap phone; logo; link | Works on low-cost phones and patchy data. |

Also record a separate 2–3 min **fallback walkthrough of the hosted web app** (screen capture) linked in README.

## 13.3 Short deck (PowerPoint, ~8–10 slides) — `docs/deck_outline.md`

Make it with the team's deck tool; the agent writes the outline + speaker notes + exports diagrams/screenshots into `docs/deck_assets/`.

1. Title, team, challenge 3 (teacher support & training).
2. **AI/LLM usage in layers** — the 02 §2.1 diagram; table of the 6 runtime Claude roles: where called, what it does, model, guard.
3. **Core innovation**: deterministic misconception engine + LLM voice; Ravi example; transition table snippet; blind realism result (11.5) if done.
4. **Guardrails**: schema validation, number/answer guard, quote-exists guard, sources ⊆ retrieved, confidence → human review queue, deterministic fallbacks; 3 real blocked examples + rates from `eval/guards/REPORT.md`.
5. **Evaluation**: kappa vs coaches (n, value, CI), latency p50/p95, realism mean — honest.
6. **Real scenarios**: low-connectivity table, data per week, low-cost Android, WhatsApp-first, voice in Hindi/Hinglish, 15 min/week; what needs network, what degrades.
7–8. **User inputs & testing**: who, how many, 2 rounds, top findings, what changed (before/after), quotes.
9. **Future roadmap**: IVR for feature phones; Bhashini + more languages; integration with DIKSHA/Prerna and the monthly Shikshak Sankul cycle; DIET/SCERT dashboards; class-audio coaching (opt-in, school-owned); child-outcome link (evidence level 5) via assessment partners; content pipeline scaled with SCERT coaches; cost per teacher per year.
10. Privacy & safety (DPDP), ask.

## 13.4 Roadmap content (README + deck)

Near term (pilot, Dec–Feb): 30–100 teachers with one DIET; 16 moves; kappa ≥ 0.7 on 100 double-coded rehearsals; Sankul mode in monthly meetings. Mid term: IVR channel, Bhashini/State speech stack, 3 more languages, integration with state teacher apps, child-outcome evidence. Systems: ARP digest feeds existing mentoring visit apps; trainer view aligned to SCERT module structure.

## 13.5 Submission checklist (`docs/submission_checklist.md` — tick in PROGRESS.md)

- [ ] Hosted URL live, freeze tag deployed, `/healthz` SHA matches tag
- [ ] All 7 demo logins work; passwords rotated and entered in the form only
- [ ] 3–5 sample inputs listed + playable
- [ ] README complete (13.1)
- [ ] `.env.example`, LICENSE, no secrets (gitleaks), no real user data in repo
- [ ] YouTube video public, ≤ 3:00, link in README and form
- [ ] Fallback walkthrough video
- [ ] Deck (PPTX) uploaded
- [ ] Evaluator GitHub IDs added (if provided)
- [ ] Submitted **31 Oct** (a day early), confirmation screenshot saved
