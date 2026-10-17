# Project summary

Status as of 2026-10-17, on branch `feat/async-rbac-rewrite`. Not merged into `main` and not pushed.

## What was built

The original synchronous implementation (SQLAlchemy sync, psycopg, Celery and Redis, refresh tokens) was replaced with an async rewrite that follows the assessment brief in `PROJECT_REQUIREMENT.md`.

| Area | Where | Notes |
|---|---|---|
| Config, security, errors | `app/core/` | pydantic-settings; pwdlib bcrypt and PyJWT HS256; `AppException` hierarchy with global handlers returning `{"error": {"code", "message", "details"}}` |
| DB layer | `app/db/` | Async engine and session factory; `Base` with a constraint naming convention |
| Models and schemas | `app/models/`, `app/schemas/` | `roles`, `users`, `tasks` with native PG enums. Request schemas use `extra="forbid"` |
| Dependencies | `app/api/deps.py` | `get_db`, `get_current_user`, `require_roles(*roles)` |
| Auth | `app/services/auth_service.py`, `app/api/routes/auth.py` | `POST /auth/register` (always USER) and `POST /auth/login` (OAuth2 form, so Swagger Authorize works) |
| Tasks | `app/services/task_service.py`, `app/api/routes/tasks.py` | CRUD-style endpoints from the spec, plus `GET /tasks/{id}` |
| Users | `app/services/user_service.py`, `app/api/routes/users.py` | `GET /users/me`; `GET /users` for ADMIN and MANAGER, which feeds the frontend's assignee picker |
| Migrations | `alembic/` | `0001` schema, `0002` role seed. `alembic check` reports no drift |
| Admin bootstrap | `scripts/seed_admin.py` | Idempotent. Uses `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` and runs on container start |
| Docker | `Dockerfile`, `docker-compose.yml` | Multi-stage, non-root image. Services: db, api, nginx frontend, plus a `test` profile |
| Frontend | `frontend/`, `nginx/` | The existing vanilla JS dashboard, adapted to the new API |
| Tests | `tests/` | 300 tests against real PostgreSQL, all passing (`docker compose --profile test run --rm test`) |
| Docs | `README.md`, `docs/ERD.md`, `docs/postman_collection.json` | |

## Key decisions

- **RBAC is checked twice.** `require_roles` gates the routes, and the task service re-checks the whole matrix. The service is safe even when called without the route.
- **Visibility is defined once.** `_VISIBLE_VIA` in `task_service.py` drives both the SQL `WHERE` clause used by the list query and the Python check for single tasks, so the two can't drift apart.
- **The transition map is an explicit constant.** `ALLOWED_TRANSITIONS`:
  - PENDING → IN_PROGRESS or COMPLETED
  - IN_PROGRESS → PENDING or COMPLETED
  - COMPLETED → IN_PROGRESS
  - Setting the current status again returns 400.
- **Check order** is 401, then the role gate (403), then a missing task (404), then not permitted (403), then 422 or 400.
- **Row locks.** `SELECT ... FOR UPDATE` on assign and status changes prevents racing transitions.
- **The role comes from the DB, not the JWT.** A role change applies immediately, and a forged role claim does nothing.
- **Services own their commits.** `Task` uses `eager_defaults`, so timestamps come back via `RETURNING` without a refresh.
- **Test isolation:** each test runs inside an outer transaction that is rolled back, with service commits turned into savepoints.
- **pwdlib instead of passlib.** passlib is unmaintained and breaks with bcrypt 4.1 and later. Passwords over 72 bytes are rejected at registration and fail cleanly at login.

## Assumptions

These are documented in full in the README.

- A MANAGER can only assign or update the status of tasks they created or are assigned to.
- A task that exists but is out of scope returns 403, not 404.
- Registration always creates a USER. A `role` field in the request is rejected with 422.
- An unknown assignee returns 422 `ASSIGNEE_NOT_FOUND`. Any existing user can be an assignee.
- `due_date` is a date and cannot be in the past at creation.
- Emails are stored lower-cased.
- A completed task can be reopened to IN_PROGRESS.
- There are no refresh tokens.

## Unfinished / next steps

1. **No API to change a user's role.** You get a MANAGER through SQL, which is shown in the README under Assumptions. A `PATCH /users/{id}/role` endpoint for ADMIN would make demos and the Postman flow easier.
2. **Your local `.env` needs updating before `docker compose up`.** I did not read or change it.
   - `SECRET_KEY` must now be at least 32 characters, or the API refuses to start.
   - Add `FIRST_ADMIN_EMAIL` and `FIRST_ADMIN_PASSWORD`.
   - The old `CELERY_*` / `REDIS_*` variables are ignored and can be removed.
   - Compose overrides `DATABASE_URL` for the api container.
3. **The old Docker volume `pg17_data` is orphaned.** The new stack uses `postgres_data`. Remove the old one with `docker volume ls` and `docker volume rm` once you no longer need its data.
4. **The frontend was not tested in a browser.** The JS passes `node --check`, and every API call it makes was exercised with curl through nginx.
5. **Redis (optional in the brief) is not implemented.** Good candidates: login rate limiting, or caching `GET /users`.
6. **Timestamps use PostgreSQL `now()`, which is the transaction start time.** Switch to `clock_timestamp()` if you need wall-clock precision within long transactions.
7. **The branch is ready to review and merge** (`git checkout main && git merge feat/async-rbac-rewrite`).

## Running things

```bash
# Local Python 3.12 venv already exists at .venv
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .

# Full stack (needs .env, see step 2 above)
docker compose up -d --build                  # API :18000, frontend :18080, db :15432
docker compose --profile test run --rm test   # test suite in docker
```
