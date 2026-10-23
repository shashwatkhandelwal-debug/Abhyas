# Submission checklist

Deadline: 1 Nov 2026 23:59 IST. Internal freeze: 31 Oct 18:00 IST. Submit on 31 Oct. Tick items in PROGRESS.md as they close.

- [ ] Hosted URL live, freeze tag deployed, `/healthz` SHA matches the tag
- [ ] All seven demo logins work; passwords rotated on Render and entered in the form only
- [ ] 3–5 sample inputs listed (README §2) and playable; five WAVs rendered with `make samples` and listened to
- [ ] README placeholders replaced by a person (hosted URL, video link, fallback link, team photo, WhatsApp number; the list is at the top of `PROGRESS.md`), measured latency and data figures added only if measured
- [ ] `.env.example`, LICENSE present; gitleaks green; no real user data in the repo
- [ ] `eval/latency/REPORT.md` regenerated against the hosted URL with real keys (`--url`), status PASSED or honestly FAILED
- [ ] `eval/guards/REPORT.md` regenerated (`make eval-guards`, with `EVENTS=` from the hosted run if available)
- [ ] YouTube video public, ≤ 3:00, link in README and the form
- [ ] Fallback walkthrough video linked
- [ ] Deck (PPTX) uploaded
- [ ] Evaluator GitHub IDs added if provided
- [ ] `make audit` reviewed; no unresolved high-severity findings
- [ ] Submitted 31 Oct; confirmation screenshot saved

## Features that must be real or removed from the docs before freeze
The ARP digest, trainer view, coach console and admin page are shipped and in the README credentials table. WhatsApp live needs Meta credentials and approval: if it is not set up, the README says the web app is the channel under test. If anything else is not working at the freeze, delete its row in the README credentials table and its path in `docs/demo_runbook.md`.

## Submission material (documents in `docs/submission/`)
- [ ] Build explainer read by the person who will explain the build live (`BUILD_EXPLAINER.md`)
- [ ] Deck built from `DECK_OUTLINE.md`; numbers re-copied after the final run
- [ ] Video recorded from `VIDEO_SCRIPT.md`, link in README and form
- [ ] Roadmap pages (`ROADMAP.md`) reviewed: every claim built, partly built or intended
- [ ] At least one mentor session run with `MENTOR_SESSION_KIT.md`; change-log has commit SHAs
- [ ] `REAL_DEVICE_CHECKLIST.md` filled on a real phone (or the deck says it was not done)
