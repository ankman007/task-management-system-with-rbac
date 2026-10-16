#!/bin/sh
set -e

# Only the API container runs migrations/seeding, so the worker doesn't race it
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "Running database migrations..."
    alembic upgrade head
    echo "Seeding default roles..."
    python seed.py
fi

exec "$@"
