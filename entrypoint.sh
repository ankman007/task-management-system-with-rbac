#!/bin/sh

# Fail immediately if any command exits with a non-zero status
set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "🚀 Database is up to date. Starting FastAPI application..."
exec "$@"