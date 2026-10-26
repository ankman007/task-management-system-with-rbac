# Project summary

Status as of 2026-10-26, on `main`. The async rewrite (formerly `feat/async-rbac-rewrite`) was fast-forwarded into `main`, and the production-readiness work below was committed on top.

## What exists

| Area | Where | Notes |
|---|---|---|
| Config, security, errors | `app/core/` | pydantic-settings with production safety checks; pwdlib bcrypt and PyJWT HS256; `AppException` hierarchy returning `{"error": {"code", "message", "details"}}` |
| DB layer | `app/db/` | Async engine and session factory; `Base` with a constraint naming convention |
| Models and schemas | `app/models/`, `app/schemas/` | `roles`, `users`, `tasks` with native PG enums. Request schemas use `extra="forbid"` |
| Dependencies | `app/api/deps.py` | `get_db`, `get_current_user`, `require_roles(*roles)` |
| Auth | `auth_service.py`, `routes/auth.py` | Register (always USER) and OAuth2-form login |
| Tasks | `task_service.py`, `routes/tasks.py` | Spec endpoints plus `GET /tasks/{id}`. Visibility in SQL, row locks, explicit transition map |
| Users and roles | `user_service.py`, `routes/users.py` | `GET /users/me`; `GET /users` (ADMIN/MANAGER); `PATCH /users/{id}/role` (ADMIN, last-admin protected) |
| Migrations | `alembic/` | `0001` schema, `0002` role seed. Repeatable; `alembic check` shows no drift |
| Admin bootstrap | `scripts/seed_admin.py` | Idempotent. Never promotes an existing account; rejects example credentials in production |
| Frontend | `frontend/` | Vanilla JS dashboard calling `/api`. Admin role management on the Users page |
| Reverse proxy | `deploy/nginx/` | nginx image with the frontend baked in, `/api` proxy, login rate limit, security headers and CSP |
| Docker | `Dockerfile`, `docker-compose.yml`, `docker-compose.dokploy.yml` | Dev stack and production (Dokploy) stack |
| CI | `.github/workflows/ci.yml` | Ruff, migration round-trip, pytest on PostgreSQL, image builds |
| Tests | `tests/` | About 390 tests on real PostgreSQL, including true-concurrency tests |
| Docs | `README.md`, `docs/DEPLOYMENT.md`, `docs/ERD.md`, `docs/postman_collection.json` | |

## Decisions made in this round

- **Role management.** `PATCH /users/{id}/role` is ADMIN-only at both the route and the service. Setting the current role is a no-op.
  - The last ADMIN can't be demoted (`409 LAST_ADMIN`).
  - The service locks all ADMIN rows in id order, which avoids deadlocks. It then re-checks that the caller is still an ADMIN, so a just-demoted admin's in-flight request is refused.
  - Mutation checks confirmed the concurrency tests fail without each safeguard.
- **The seed no longer auto-promotes existing accounts.** Previously, anyone who registered `FIRST_ADMIN_EMAIL` before the first deploy would have been made ADMIN.
- **Single origin.** nginx serves `/` (dashboard), `/api/*`, `/docs` and `/openapi.json`.
  - The app runs with `ROOT_PATH=/api`. Starlette strips the prefix when it's present, so routes answer with or without it, and tests and direct access are unchanged.
  - Swagger's `tokenUrl` includes the prefix (`/api/auth/login`), because Swagger UI resolves it against the `/docs` page URL. That makes **Authorize** work through the proxy; it was verified by clicking Authorize in a real browser.
- **Production safety in config.** With `ENVIRONMENT=production`, startup fails on a placeholder `SECRET_KEY`, `ALLOWED_HOSTS=*` or `CORS_ORIGINS=*`.
  - New settings: `ALLOWED_HOSTS` (TrustedHostMiddleware; localhost always allowed for the healthcheck), `ROOT_PATH`, `DOCS_ENABLED`.
  - CORS never allows credentials.
- **Dokploy conventions copied from Ecommerce Store:**
  - a Compose app with no host ports;
  - nginx as the only service on the external `dokploy-network`;
  - pre-start steps in the app container;
  - nginx `depends_on` a healthy API, so a failed migration fails the deploy;
  - named volume, JSON log rotation, `restart: unless-stopped`;
  - a baked nginx image (no bind mounts).
- **Security hardening:**
  - nginx rate-limits login/register (10/min, burst 10, keyed on `CF-Connecting-IP`) and caps bodies at 1 MB;
  - security headers and a CSP on the dashboard;
  - no `Server` version headers;
  - the API runs as uid 1000.
- **Timestamps stay on `now()`** (transaction time). Each request is one short transaction and listings break ties by id. Documented in the README (assumption 15).
- **No Redis.** There's no cache, queue or background job that needs it. Documented in the README (assumption 16).

## Verification performed (2026-10-26)

- **pytest:** full suite against PostgreSQL 17, both locally and in the dev compose `test` profile. See the final report for counts.
- **Ruff:** check and format are clean.
- **Migrations:** upgrade, `alembic check`, downgrade base and upgrade again, all clean.
- **Production compose** (`docker-compose.dokploy.yml`), run locally with a stand-in `dokploy-network`:
  - all three services healthy, and only nginx reachable;
  - 27/27 smoke checks through nginx with the production `Host` header: frontend, `/docs`, `/openapi.json`, `/api/*`, auth, RBAC, role changes, the last-admin guard, rate limiting, Host header rejection and headers;
  - `down` and `up` kept the data, and the seed was a no-op;
  - a deliberately wrong DB password made `up --wait` fail, nginx was never started, and the logs showed the cause;
  - the API runs as a non-root user.
- **Browser:** headless Edge (Playwright) on the production stack:
  - sign-up, the wrong-password message, admin role change, the last-admin error, task creation and assignment, the status workflow, the roles page and dashboard counters;
  - no console errors besides the deliberate 401 and 409.

## Not done / needs someone with access

1. **Actual deployment.** I had no Dokploy, Cloudflare or server access, so the steps in `docs/DEPLOYMENT.md` sections 2–6 must be done in the dashboards.
2. **Cloudflare 526 until deployed.** The server is `103.181.227.8`, and Traefik on it is reachable directly (Ecommerce Store uses a Let's Encrypt certificate there; no tunnel). `task-mgmt` returns 526 only because Traefik has no router or certificate for it yet. Deploying with the Dokploy domain set to HTTPS + Let's Encrypt (DEPLOYMENT.md, Route A) fixes it. Keep the Cloudflare `A` record on `103.181.227.8`.
3. **The old pre-rewrite local stack is still running** (`task_manager_frontend`, `task_manager_db`, `task_manager_redis`, holding ports 18080/15432/16379, with the volume `pg17_data`). Stop it before using the new `docker compose up` on the default ports. Its data is the old schema and isn't used by the new stack.
4. **Optional:** a Dokploy Volume Backup schedule for the database volume (`<project>_postgres_1`), and an uptime monitor on `/api/health`.

## Running things

```bash
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
docker compose up -d --build                  # dashboard :18080 (API at /api), API :18000, db :15432
docker compose --profile test run --rm test   # test suite in docker
```
