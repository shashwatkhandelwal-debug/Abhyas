# Submission checklist

Deadline: 1 Nov 2026 23:59 IST. Internal freeze: 31 Oct 18:00 IST. Submit on 31 Oct. Tick items in PROGRESS.md as they close.

- [ ] Hosted URL live, freeze tag deployed, `/healthz` SHA matches the tag
- [ ] All seven demo logins work; passwords rotated on Render and entered in the form only
- [ ] 3–5 sample inputs listed (README §2) and playable; five WAVs rendered with `make samples` and listened to
- [ ] README complete, TODO(human) markers replaced (URL, video link, WhatsApp number, measured latency and data figures)
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
ARP digest (T32), trainer view (T33), coach console (T34), admin page (T35), WhatsApp live (needs Meta approval). If one is not shipped, delete its row in the README credentials table and its path in `docs/demo_runbook.md`.
