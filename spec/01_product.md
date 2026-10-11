# 01 — Product

## 1.1 Problem

Government primary teachers in UP and similar states receive FLN (NIPUN Bharat) training in short bursts (block/cluster trainings, monthly Shikshak Sankul meetings). Between trainings they have **no safe place to practise** the classroom moves they were taught (e.g. using bundles and sticks for regrouping, asking a child to explain a wrong answer instead of telling the answer). Training fidelity decays; trainers and ARPs (Academic Resource Persons) see **attendance**, not **adoption**.

## 1.2 Solution (one paragraph)

Abhyas is a **voice-first practice partner** reached over **WhatsApp** (and an equivalent light web chat). Each week a teacher, in ~15 minutes and in Hindi:

1. **Learns** one teaching move from the state FLN module (≤ 2-min voice note).
2. **Explains it back** in her own words (≤ 1-min voice note) → AI scores fidelity against the move's key points and tells her the one point she missed.
3. **Hears a model teacher** handle the scenario (optional).
4. **Rehearses** by voice with **three simulated children** whose mistakes are **computed by a deterministic rule engine** (Claude only turns the engine's answer into a natural child's line).
5. Gets **rubric feedback**: one strength, one change, exact words to try — every score backed by a quote from her own transcript — and **retries**.
6. **Tries it in class**: a peer runs a 5-minute checklist, or she answers 2 reflection questions.
7. Can **ask questions any time**; answers cite the state guides; low-confidence questions go to her ARP; a 2-day follow-up asks "did it work?".

Back-end outputs: an **evidence ladder** per teacher × move (rehearsed → self-reported → peer-observed → ARP-observed → children improved), a **weekly ARP digest** (consenting teachers only), and a **trainer view** for DIET/SCERT by module × batch (groups ≥ 10 only).

## 1.3 Why this is novel (keep these claims true in code)

| Claim | Where it's enforced |
|---|---|
| Simulated children make **realistic, persistent, research-based mistakes** — LLM role-play students are known to solve correctly or give in too quickly | `04_rule_engine.md`; guard in `05` rejects any child line containing an answer the engine didn't produce |
| Children only improve when the teacher uses a move that actually addresses the misconception; **telling the answer causes a parrot-then-relapse** | transition table + relapse test |
| Feedback is **evidence-cited** — every rubric score quotes the teacher's own words | coach guard |
| Measures **adoption, not attendance** | evidence ladder |
| Privacy by design — individual scores never go upward without consent; aggregates suppressed below n = 10 | `03` RLS + `09` + tests |

## 1.4 Users and roles

| Role | Who | Channel | Sees / does |
|---|---|---|---|
| `teacher` | Govt primary teacher, Classes 1–3, Hindi-speaking, low-cost Android, patchy data | WhatsApp (primary), web chat (PWA) | Weekly loop, ask questions, own progress |
| `arp` | Academic Resource Person for a cluster (~20–40 teachers) | Web + WhatsApp digest template | Weekly digest for **consenting** teachers in own cluster; log classroom observations; answer escalated questions |
| `trainer` | DIET/SCERT faculty | Web | Aggregates by module × batch; n<10 suppressed; no names |
| `coach` | FLN expert (content reviewer) | Web review console | Approve/edit moves; review low-confidence scores; answer queued questions |
| `admin` | Team | Web | Users, fast-forward timers (demo), cost/latency dashboards, content publish |

## 1.5 User constraints the design must respect

- **Voice first, Hindi/Hinglish.** Text accepted everywhere. All teacher-facing copy in simple Hindi (Devanagari). Hinglish (Roman) input must work.
- **~15 min/week.** Every step is skippable except consent.
- **Low-cost Android, 2G/3G, intermittent data.** Voice notes are Opus ~16 kbps (~120 KB/min). Web pages < 150 KB. Text always sent before (or with) audio so a dropped audio download never blocks progress.
- **Nothing to install** (WhatsApp) — web chat is a PWA, installable but optional.
- **Teacher dignity.** Feedback tone: respectful, colleague-to-colleague ("आपने…", never "तुमने…"). One strength first. Never shaming.
- **Children's privacy.** Class audio is **off by default**. Children are never scored or identified.

## 1.6 Scope for the 1 Nov build

### IN (must work on the hosted deploy)

- Web teacher chat with hold-to-record voice, text input, audio playback, buttons; low-network ("लाइट मोड") mode.
- WhatsApp channel on Meta Cloud API (works when credentials exist; mocked in tests; shown in demo video).
- Onboarding: consent → profile (3 questions) → short placement role-play → personal move order.
- Full weekly loop for **4 moves** (3 numeracy, 1 literacy) from `content-seed/moves/`.
- Rule engine with 12 bug rules (9 numeracy, 3 literacy), 3 personas, full transition table.
- Claude roles: intent_router, act_tagger, child_voice, coach, fidelity_checker, guide_answerer (runtime); move_generator, move_reviewer, model_teacher (build-time).
- STT/TTS via one hosted Indian provider + mocks; distinct child voices via pitch shift.
- Ask-any-time with retrieval over ingested guide chunks; ARP escalation; 2-day follow-up job.
- Evidence ladder; ARP digest page; trainer view with suppression; coach review console; admin page with fast-forward.
- Seeded **clearly-labelled demo data** for ARP/trainer views (synthetic teachers), plus real pilot data when available.
- Consent flows, data retention (audio deleted after transcription), cost log, latency log.
- Eval harness: kappa, latency, realism; user-testing protocol and evidence folder.
- README, LICENSE (MIT), `.env.example`, AI-services list, sample inputs, demo video script, deck outline.

### OUT (roadmap only — mention in deck, do not build)

- IVR / phone-call version for feature phones.
- Class-audio analysis of real lessons.
- Integration with state teacher platforms (DIKSHA, Prerna UP), Bhashini as default speech stack, VallamAI child assessment link (evidence level 5).
- Self-hosted GPU speech models.
- Languages beyond Hindi.

## 1.7 Success metrics (report honestly in `eval/`)

| Metric | Target |
|---|---|
| AI coach vs FLN coach agreement | quadratic-weighted kappa ≥ 0.7 (report actual n, even if small) |
| Explain-back scoring vs coach | kappa ≥ 0.7 |
| Realism of AI children (teacher rating) | mean ≥ 4/5 |
| Latency voice-in → voice-out | p95 < 20 s |
| Pilot engagement | ≥ 50% of pilot teachers complete one full loop |
| Guard failure rate (child_voice) | < 5% of turns reach template fallback |
