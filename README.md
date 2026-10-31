# Abhyas (अभ्यास)

Abhyas is a voice-first Hindi practice partner for government primary-school (FLN, Classes 1 to 3) teachers.
A teacher learns one teaching move a week, then rehearses it with simulated children (Ravi, Priya and Aman, each with a different hidden mistake), gets feedback that quotes their own words, and tries it in class.
Built by Team Asymptotes for the AI for Foundational Learning Hackathon 2026, Challenge 3: Teacher Support and Training.

## Live demo

**https://abhyas-vjh5.onrender.com**

It runs on Render's free tier, which sleeps when idle: **the first load can take about 50 seconds**. Later loads are fast. The login page is kept by the service worker, so a second visit shows it at once.

### Test credentials

Password for every account: `abhyas_admin_2026` (the public demo password; all data behind these accounts is synthetic).

| Username | Role | What to look at |
|---|---|---|
| `teacher.demo1` | Teacher, new | Onboarding, then the first weekly loop from the learn step |
| `teacher.demo2` | Teacher, practised | Chat opens in a one-on-one scene with Ravi (43 − 27): continue it, get coach feedback, retry, diagnose a child |
| `teacher.demo3` | Teacher, experienced | Three modules done: the next module, the progress page, adaptive next practice, asking the handbook |
| `arp.demo` | ARP (cluster mentor) | Weekly digest, visit list, an escalated question to answer |
| `trainer.demo` | Trainer (DIET) | Module by batch view and the n < 10 suppression (batch KNP-B3) |
| `coach.demo` | FLN coach | Review queue, calibration labelling, move-card review |

An `admin` account (latency, guardrail stats, reset demo) is created by the seed too; its password is set separately by `ADMIN_PASSWORD`, so it is not in the table.
The teacher logins are shared: a chat resets to its starting state when you log in or out, so pick one nobody else is using.

### Five inputs to try

Type these in the teacher chat (voice works too, with a microphone and a Sarvam key).

| # | Log in as | Type | What happens |
|---|---|---|---|
| 1 | `teacher.demo2` | `52 - 17` | A new problem for Ravi. He answers with his own mistake (45): he takes the smaller digit from the bigger one in each column. |
| 2 | `teacher.demo2` | `explain` | Ravi explains his steps on the current problem, mistake included. He never gets the answer from the model; his answers come from the rule engine. |
| 3 | any teacher | `delete my data` | Asks you to confirm, with Delete and Cancel buttons. Nothing is erased until you confirm. |
| 4 | `teacher.demo3` | `सवाल: खिलौना आधारित शिक्षण का क्या महत्व है?` | A handbook answer with a source chip (document and page). |
| 5 | `teacher.demo3` | `How do I teach place value to Class 1 children?` | An answer from the handbook, in Hindi, with its source. Questions in English are understood. |

Two behaviours that look like bugs but are not: on a learn step, plain typed text gets "tap one of the two buttons" unless it starts with `सवाल:` or is clearly a how-to question; and a question the documents cannot answer is not guessed, it is sent to the ARP's review list.
Ready-made chips for the same inputs are in the suggestions panel.

---

## How AI is used

The central design rule: **a deterministic rule engine owns each simulated child's state and answers. The language model only gives the child a voice and writes coach feedback.** No model ever decides what a child answers (tests enforce it).

| Layer | What happens |
|---|---|
| **Input** | Hindi or Hinglish voice note (speech to text), typed text, or a button tap. Text is normalised (NFC) at every boundary. |
| **Processing** | Claude Haiku classifies the intent and tags what the teacher just did (asked the child to explain, told the answer, and so on). The rule engine (`backend/app/rule_engine/`) updates the child's hidden state and picks the child's answer. Claude Haiku then renders that answer in the child's voice. Claude Sonnet writes coach feedback, scores explain-back fidelity, and answers handbook questions from retrieved excerpts (BM25 over the committed chunks). |
| **Guardrails** | Every model output is checked against a strict schema, then guarded: a child's numbers must belong to the rule engine's permitted set; a coach's quoted words must exist in the real conversation; a guide answer may cite only the passages that were retrieved. A failed guard is retried once, then replaced by a template. Every failure is logged (`backend/app/llm/guards.py`, `guard_stats.py`). |
| **Evaluation** | Latency logs and guard-failure counts (admin page); the harnesses in `eval/` for latency, guard cases, retrieval recall, classifier accuracy, and coach agreement (kappa). No coach double-coding has been done, so there is no kappa figure yet. |
| **Output** | Text always, plus a synthesised voice reply (a distinct voice per child), buttons, and the ARP and trainer views built from consented, aggregated data. |

### External AI services

| Service | Model | Used for | Called from | Key |
|---|---|---|---|---|
| Anthropic Claude Haiku 5.5 | `claude-haiku-5-5` | Intent routing, act tagging, child voice, question, diagnosis, class-struggle and teaching-skill classification, translation | `backend/app/llm/client.py`; roles in `backend/app/llm/roles/` | `ANTHROPIC_API_KEY` (model: `CLAUDE_MODEL_FAST`) |
| Anthropic Claude Sonnet 5.5 | `claude-sonnet-5-5` | Coach feedback, explain-back fidelity, handbook answers, content generation | same | `ANTHROPIC_API_KEY` (model: `CLAUDE_MODEL_SMART`) |
| Sarvam AI speech to text | `saaras:v4` | Teacher voice notes | `backend/app/speech/stt.py` | `SARVAM_API_KEY` |
| Sarvam AI text to speech | `bulbul:v3` | Children's and coach's voice replies | `backend/app/speech/tts.py` | `SARVAM_API_KEY` |
| Google Gemini | `gemini-3.8-flash`, `gemini-3.8-flash-tts` | Optional alternative or fallback for speech (`backend/app/speech/gemini.py`) | `backend/app/speech/stt.py`, `tts.py` | `GEMINI_API_KEY` |

**About Gemini, plainly:** the code can use Gemini for speech, as the primary or as a fallback. In the defaults and in `.env.example`, `STT_PROVIDER` and `TTS_PROVIDER` are `sarvam` and the fallbacks are `none`, so **Sarvam serves all speech today** and Gemini is not called unless you set it. Meta WhatsApp Cloud API support also exists in the code (`WHATSAPP_*`) and is off by default.

**Spend caps built into the app:**
- Claude: a daily token budget, `LLM_DAILY_TOKEN_BUDGET` (3,000,000 tokens a day by default); once it is used up, model calls are refused for the rest of that day (India time).
- Speech: `SPEECH_DAILY_BUDGET_INR` (₹50 a day) and `SPEECH_TOTAL_BUDGET_INR` (₹500 in total); past a cap, speech is refused and the chat stays text-only (`backend/app/speech/spend.py`).
- Per-user rate limits on chat, login and translation.

Every service has a mock chosen by environment variable. With an empty `.env` the whole product runs locally on mocks.

---

## Privacy

- **No child data.** The children are simulated. No real child's data is collected or stored.
- **Consent.** Setup asks consent to use the service. Sharing a teacher's scores with their ARP is a separate opt-in, off by default and changeable from the menu.
- **n < 10 suppression.** The trainer and district views show only aggregates for any batch or cluster with fewer than 10 teachers.
- **Audio is not kept.** A voice note is held in memory while it is transcribed, then discarded. Only the text is stored.
- **Delete my data.** A teacher can type `delete my data` (or use `/teacher/delete`) to erase their account and everything attached to it, after a confirmation. Inactive transcripts are also purged after `DATA_RETENTION_DAYS` (90).
- **Phone numbers** (WhatsApp only) are stored as a salted hash plus a Fernet-encrypted copy.
- **Cross-border processing.** Voice and text go to Sarvam and Anthropic APIs. A legal review against the DPDP Act 2023 has not been done.
- **Shared devices.** The offline copy of a chat belongs to one account: it is cleared on logout, on session expiry and when a different account logs in on the same browser.

---

## Offline and low connectivity

Pages are server-rendered HTML with a little vanilla JavaScript and one CSS file, kept under 150 KB on first load (audio excluded), for low-cost Android phones on 2G or 3G.

| | Needs a connection? | Without one |
|---|---|---|
| Opening the app again | Only the first visit | The service worker keeps the login page and static files |
| Reading the offline page | No | Shows a checklist and the last 50 messages of **your** account (`/offline.html`) |
| Sending text or a voice note | Yes, to be answered | It is queued on the phone and sent when the network returns; the message shows a clock, then a tick |
| Practice replies (the children, the coach) | Yes | Not available offline; they need the server and the models |
| Audio playback | On demand | Lite mode skips automatic audio; text is always shown first |
| A sleeping server | | The phone retries quietly for about 30 seconds before saying so |

---

## Run it locally

You need Python 3.11 or newer, Docker (for Postgres with pgvector) and ffmpeg (for audio). Node.js is needed only for the JavaScript tests.

```bash
git clone <this repository> abhyas && cd abhyas
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env                 # leave the API keys empty to run on mocks
docker compose up -d db              # Postgres 16 + pgvector on port 5432
alembic upgrade head                 # create the schema
python -m backend.app.db.seed        # content chunks and the demo accounts
uvicorn backend.app.main:app --port 8000
```

Open http://localhost:8000. `GET /healthz` answers `{"status":"ok"}`.

- The database settings in `.env.example` match `docker-compose.yml`. Use the compose file at the repository root; the `make db-up` target points at `infra/docker-compose.yml`, which uses a different password.
- To log in with the same password as the hosted demo, set `DEMO_PASSWORD=abhyas_admin_2026` (and `ADMIN_PASSWORD`) in `.env` **before** you run the seed command. With the placeholders from `.env.example` the password is `change-me-demo-password`.
- On Windows, set `PYTHONUTF8=1` first, or the seed log prints encoding errors (the seed still completes).
- If you have `make`: `make setup`, `make db-migrate`, `make db-seed` and `make dev` wrap the same steps.

### Environment variables (`.env.example`)

Every variable is listed there with a placeholder and a comment. The groups:

| Group | Variables | Notes |
|---|---|---|
| Server | `ENVIRONMENT`, `PORT`, `LOG_LEVEL`, `PUBLIC_BASE_URL`, `GIT_SHA` | `ENVIRONMENT=production` refuses to start with placeholder secrets |
| Database | `DATABASE_URL`, `ALEMBIC_DATABASE_URL` | Async URL for the app, plain URL for Alembic |
| Security | `SESSION_SECRET`, `PHONE_HASH_SALT`, `PHONE_ENC_KEY`, `DEMO_PASSWORD`, `ADMIN_PASSWORD` | Generate your own; production rejects the placeholders |
| Claude | `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL_*`, `LLM_DAILY_TOKEN_BUDGET` | Empty key means the mock model |
| Speech | `STT_PROVIDER`, `TTS_PROVIDER`, `*_FALLBACK_PROVIDER`, `SARVAM_*`, `GEMINI_*`, `BHASHINI_*`, `MOCK_STT_TEXT` | Empty keys mean mock speech |
| WhatsApp | `WHATSAPP_*` | Off unless `WHATSAPP_ENABLED=true` |
| Demo | `DEMO_MODE`, `SERVE_IN_REVIEW_TO_DEMO`, `SEED_ON_BOOT`, `PREWARM_ON_BOOT` | `SEED_ON_BOOT` is for one deploy on a host without a shell |
| Optional | `VOYAGE_API_KEY`, `VOYAGE_MODEL`, `SENTRY_DSN` | Voyage is not used by default |

---

## Tests

```bash
ruff check .
mypy --strict backend/app
pytest                                          # unit tests; integration tests are skipped without a database
node --test backend/tests/js                    # chat.js, IndexedDB and service worker behaviour
```

The database-backed tests (`backend/tests/integration/`) and the browser tests (`backend/tests/e2e/`, Playwright) run only when `TEST_DATABASE_URL` points at a scratch Postgres with pgvector, for example `postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`. They create and drop their own databases. `make test` runs the first three commands. Tests never call a real external service.

Two things to know on a fresh checkout:
- The settings read `.env`, so a few configuration tests (`test_auth`, `test_config`, `test_whatsapp_channel`) fail if your `.env` holds real passwords or the empty keys copied from `.env.example`. Run the tests without a `.env` (or in a different directory copy).
- `backend/tests/unit/test_page_ocr.py` imports `pymupdf`, which `pyproject.toml` does not list. Run `pip install pymupdf` first, or skip that file. It is needed only to re-ingest source PDFs.

---

## Known limitations

- **No teacher field study yet.** No real teacher has used Abhyas, so there is no measured learning effect, no realism rating, and no coach agreement (kappa) figure. The moves still carry the "समीक्षा में" (in review) label.
- **Free-tier hosting.** The hosted app sleeps when idle (about 50 seconds to wake) and runs one instance. The free Postgres instance **expires on 2026-11-20**, after which the hosted demo needs a new database.
- **Scope.** Four teaching moves (three numeracy, one literacy), Hindi and Hinglish speech only, and the rule engine models a closed set of research-backed mistakes.
- **WhatsApp** needs Meta business verification and approved templates; the web chat is the complete experience.
- The Class 1 Ganit guide has no two-digit subtraction with regrouping, so the demo move for it is not backed by an official page, and the app says so instead of guessing.

---

## Licence

The code is released under the MIT licence: see [LICENSE](LICENSE).

### CONTENT_NOTICE

The MIT licence covers **the code only**. The material under `content/` that is derived from published documents belongs to its original publishers and is included only so that the handbook Guide can answer teachers' questions with a source and page. **Redistribution terms for these documents have not been cleared**; if you reuse this repository, check each publisher's terms first.

- NIPUN Bharat Guidelines for Implementation (Ministry of Education, Government of India, 2021)
- Vidya Pravesh (NCERT)
- NISHTHA FLN (NCERT)
- UP Samagra Shiksha teacher guides, Class 1, Ganit and Bhasha (Government of Uttar Pradesh)

What is committed is processed text, in `content/chunks/*.jsonl` (passages with page numbers, plus Hindi summaries and keywords written by us), and `content/sources/sources.yaml` (title, URL, checksum). The source PDFs are not in the repository, and neither is the OCR page cache of the two UP guides (`content/sources/ocr_cache/` is git-ignored). Details and limits are in `content/sources/README.md`. The teaching-move cards, persona cards and the Hindi message catalog are original work of the team.
