# Infrastructure & Deployment (`infra/`)

Contains local development orchestration and container images for Abhyas services.

## Services
- `db`: PostgreSQL 16 with `pgvector` extension enabled for semantic guide search.
- `redis`: Redis 7 Alpine cache and async task queue broker.
- `backend`: FastAPI application server.
- `worker`: Arq scheduled worker processing utility templates and follow-ups.

## Quick Start
```bash
docker-compose -f infra/docker-compose.yml up -d
```
