# Abhyas (अभ्यास)

> **AI for Foundational Learning Hackathon 2026 · Challenge 3: Teacher Support and Training**  
> Team Asymptotes: Shashwat Khandelwal · Vedant Arora · Divyansh Agrawal

A **voice-first WhatsApp practice partner** for government primary school teachers (FLN, Classes 1–3) between trainings, in Hindi. 

Each week a teacher:
1. **Learns** one teaching "move" from the state FLN module (2-min voice note).
2. **Explains it back** in her own words (1-min voice note, scored for fidelity).
3. **Hears a model teacher** handle the scenario.
4. **Rehearses** it by voice with **three AI-simulated children** whose mistakes are **computed by a rule engine** (Claude only voices the lines).
5. Gets **rubric feedback** (one strength, one change, exact words to try) and retries.
6. **Tries it in class** (peer 5-minute checklist or guided reflection).
7. Can **ask questions any time** (answers cite state guides; follow-up after 2 days; hand-off to the ARP).

---

## Monorepo Layout

```
abhyas/
├── ARCHITECTURE.md                  # Single source of truth build specification
├── pyproject.toml                   # Root package & tool configs (ruff, mypy, pytest)
├── backend/                         # Python 3.11, FastAPI server & async workers
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory, routes, lifespans
│   │   ├── config.py                # Pydantic settings & all thresholds (no magic numbers)
│   │   ├── whatsapp/                # Webhook, signature verify, send, templates, media
│   │   ├── speech/                  # STT & TTS provider adapters
│   │   ├── sessions/                # State machine, weekly loop, 24-hr window timers
│   │   ├── rule_engine/             # Child personas, misconception rules, state transitions
│   │   ├── llm/                     # Claude client, 5 role prompts, schemas, token guards
│   │   ├── retrieval/               # pgvector search over state guides & practice library
│   │   ├── scoring/                 # Rubric scoring, explain-it-back, evidence ladder
│   │   ├── reports/                 # ARP digest, trainer aggregates (n >= 10 suppression)
│   │   ├── db/                      # SQLAlchemy models, Alembic migrations
│   │   └── jobs/                    # Scheduled jobs (weekly prompts, follow-ups, digests)
│   └── tests/                       # Unit & integration test suites
├── content/                         # Content pipeline & pedagogical validators
│   ├── sources/                     # State FLN modules, UP teacher guides, NIPUN docs
│   ├── moves/                       # Approved move cards (YAML)
│   ├── personas/                    # Child personas (YAML)
│   ├── rules/                       # Misconception bug rules as Python + unit tests
│   ├── schemas/                     # JSON Schemas for moves, personas, and rules
│   ├── pipeline/                    # Content generation, validation, review, publishing
│   └── tests/                       # Content pipeline tests
├── review-console/                  # Web app for FLN coaches to approve moves & review queue
├── trainer-view/                    # Web app for DIET/SCERT aggregates (read-only, n >= 10)
├── eval/                            # Evaluation: coach calibration, latency, realism survey
└── infra/                           # Docker Compose, Dockerfiles, and deployment configs
```

---

## Quick Start (Development)

### Prerequisites
- Python 3.11+
- PostgreSQL with `pgvector` extension
- Redis 7+
- FFmpeg (for WhatsApp OGG/Opus audio processing)

### Setup

1. **Clone & Setup Environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -e ".[dev]"
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start Local Infrastructure (Docker)**:
   ```bash
   docker-compose -f infra/docker-compose.yml up -d
   ```

4. **Run Database Migrations**:
   ```bash
   cd backend
   alembic upgrade head
   ```

5. **Start the Backend Server**:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```

---

## Key Principles & Guardrails

- **Mistakes are computed, not improvised**: LLMs never invent mathematical or phonics mistakes. The rule engine determines the exact mistake; Claude only voices the line.
- **Strict token guards**: Generated child speech lines are checked token-by-token against the rule engine output before hitting TTS.
- **Privacy by default**: Audio files are deleted immediately after transcription. No individual scores go upward without explicit teacher consent. Trainer views aggregate only groups of $n \ge 10$.
- **No magic numbers**: Every threshold is centralized in `backend/app/config.py`.
