#!/bin/sh
set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "🧪 Running Test Suite..."
pytest -p no:cacheprovider

echo "🚀 Tests passed. Starting FastAPI application..."
exec "$@"