.PHONY: audit eval-guards help setup dev db-up db-migrate db-seed test test-live eval-latency eval-kappa eval-realism content-validate content-publish samples freeze

help:
	@echo "Abhyas Makefile targets:"
	@echo "  make setup            - install dependencies and pre-commit hooks"
	@echo "  make dev              - run API + web + scheduler locally on port 8000"
	@echo "  make db-up            - start local Postgres + pgvector via docker compose"
	@echo "  make db-migrate       - apply Alembic database migrations"
	@echo "  make db-seed          - load content and demo data"
	@echo "  make test             - run ruff, mypy, and unit/integration tests (mocks only)"
	@echo "  make test-live        - opt-in tests calling real providers (skipped if keys absent)"
	@echo "  make eval-latency     - run latency benchmark suite"
	@echo "  make eval-kappa       - run coach calibration kappa evaluation"
	@echo "  make eval-realism     - run realism rating analysis"
	@echo "  make content-validate - validate move cards and content schemas"
	@echo "  make content-publish  - publish approved content release"
	@echo "  make samples          - render evaluator sample voice notes into eval/samples/audio/"
	@echo "  make freeze           - run the pre-submission freeze checklist"

setup:
	pip install -e ".[dev]"
	pre-commit install || true

dev:
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

db-up:
	docker compose -f infra/docker-compose.yml up -d db

db-migrate:
	alembic upgrade head

db-seed:
	python -m backend.app.db.seed

test:
	ruff check .
	ruff format --check .
	mypy --strict backend/app
	pytest

ci:
	ruff check .
	ruff format --check .
	mypy --strict backend/app
	pytest --cov=backend/app --cov-report=term-missing
	pytest content/tests

test-live:
	pytest -m live

eval-latency:
	python eval/latency/benchmark_latency.py

eval-kappa:
	python eval/calibration/evaluate_kappa.py

eval-guards:
	python eval/guards/guard_report.py $(if $(EVENTS),--events $(EVENTS),)

eval-realism:
	python eval/realism/survey_analysis.py

content-validate:
	python content/pipeline/validate.py

content-publish:
	python content/pipeline/publish.py

samples:
	python scripts/render_samples.py

audit:
	pip-audit --skip-editable

freeze:
	python scripts/freeze_check.py
