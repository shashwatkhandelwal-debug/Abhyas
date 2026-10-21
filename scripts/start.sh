#!/bin/sh
# Container start (spec/12 §12.2): migrate, optionally seed demo data, then serve.
# Run as `sh scripts/start.sh` so no execute bit is needed.
# SEED_ON_BOOT=true seeds demo data on this boot (Render free has no Shell);
# a failed seed is logged and startup continues.
set -e

alembic upgrade head

if [ "${SEED_ON_BOOT:-false}" = "true" ]; then
    echo "start.sh: seeding demo data (SEED_ON_BOOT=true)"
    if ! python -m backend.app.db.seed; then
        echo "start.sh: ERROR: demo data seed failed; continuing startup" >&2
    fi
fi

# Single worker per spec 12 §12.2; forwarded-allow-ips="*" for Render ingress proxy
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*" --workers 1
