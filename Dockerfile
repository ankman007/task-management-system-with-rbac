# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# base: common Python settings for every stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# ---------------------------------------------------------------------------
# builder: install runtime dependencies into a self-contained virtualenv.
# All dependencies ship manylinux wheels, so no compiler is needed.
# ---------------------------------------------------------------------------
FROM base AS builder
RUN python -m venv "$VIRTUAL_ENV"
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# builder-dev: the same venv plus test/lint tooling (used by the `test` target)
FROM builder AS builder-dev
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install -r /tmp/requirements-dev.txt

# ---------------------------------------------------------------------------
# app-base: unprivileged user and the application code (owned by root, so the
# app user can read but not modify it)
# ---------------------------------------------------------------------------
FROM base AS app-base
RUN groupadd --system app && useradd --system --gid app --no-create-home app
WORKDIR /app
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app
ENTRYPOINT ["entrypoint.sh"]

# ---------------------------------------------------------------------------
# test: runtime image + dev dependencies + the test suite
#   docker compose --profile test run --rm test
# ---------------------------------------------------------------------------
FROM app-base AS test
COPY --from=builder-dev /opt/venv /opt/venv
COPY pyproject.toml ./
COPY tests ./tests
USER app
# The source tree is read-only for the app user, so skip pytest's cache dir.
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

# ---------------------------------------------------------------------------
# runtime (default target): the production API image
# ---------------------------------------------------------------------------
FROM app-base AS runtime
COPY --from=builder /opt/venv /opt/venv
USER app
EXPOSE 8000
# slim has no curl; use the interpreter that's already there.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
