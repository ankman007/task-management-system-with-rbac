#!/bin/sh
# Container entrypoint: optionally migrate and seed, then hand off to CMD.
set -e

# Only the API service sets RUN_MIGRATIONS=1; one-off containers (tests,
# `docker compose run api ...`) skip it unless asked.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "entrypoint: applying database migrations"
    alembic upgrade head
    echo "entrypoint: ensuring the first admin account"
    python -m scripts.seed_admin
fi

# exec so the app becomes PID 1 and receives SIGTERM from `docker stop`.
exec "$@"
