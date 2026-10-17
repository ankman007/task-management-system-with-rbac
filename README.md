# Task Management API with RBAC

A FastAPI service for creating, assigning and tracking tasks, with role-based access control for three roles: `ADMIN`, `MANAGER` and `USER`. It is fully async (SQLAlchemy 2.0 + asyncpg on PostgreSQL), uses JWT bearer authentication, manages its schema with Alembic, and ships with Docker Compose, a pytest suite, a Postman collection and a small web dashboard.

| | |
|---|---|
| API (Docker) | http://localhost:18000 (Swagger UI at `/docs`, ReDoc at `/redoc`) |
| Dashboard (Docker) | http://localhost:18080 |
| Database diagram | [docs/ERD.md](docs/ERD.md) |
| Postman collection | [docs/postman_collection.json](docs/postman_collection.json) |

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Quick start (Docker)](#quick-start-docker)
- [Local development (without Docker for the API)](#local-development-without-docker-for-the-api)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Architecture](#architecture)
- [Roles and permissions](#roles-and-permissions)
- [Task status workflow](#task-status-workflow)
- [Assumptions and design decisions](#assumptions-and-design-decisions)
- [Error format](#error-format)
- [API reference and curl examples](#api-reference-and-curl-examples)
- [Database and migrations](#database-and-migrations)
- [Testing and linting](#testing-and-linting)
- [Postman collection](#postman-collection)
- [Frontend](#frontend)

---

## Features

- **JWT authentication.** `POST /auth/register` and `POST /auth/login` (OAuth2 password form). Short-lived HS256 access tokens. Passwords are hashed with bcrypt.
- **RBAC enforced twice.** Reusable `require_roles(...)` dependencies gate each route, and the service layer re-checks the full rule (ownership, assignment) before touching data.
- **Visibility filtering in SQL.** `GET /tasks` and `GET /tasks/{id}` only ever load rows the caller is allowed to see. Nothing is filtered in Python after the query.
- **Validated status workflow.** An explicit transition map. `COMPLETED → PENDING` is always rejected.
- **Strict validation.** Pydantic v2 request schemas reject unknown fields (`extra="forbid"`), trim strings, and validate emails, password strength and due dates.
- **One error format.** Every error, including framework 404/405 and validation errors, returns `{"error": {"code", "message", "details"}}`.
- **Pagination and filtering.** `page` / `size` / `status` on the task list, `page` / `size` on the user list.
- **Alembic migrations.** These run automatically on container start, together with an idempotent first-admin seed.
- **Docker Compose stack.** PostgreSQL, API and an nginx-served dashboard, plus a `test` profile that runs the suite in a container.

---

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Web framework | FastAPI | Dependency injection (`Depends`) suits reusable auth and role guards. OpenAPI and Swagger come for free. |
| ORM / DB driver | SQLAlchemy 2.0 (async) + asyncpg | Non-blocking DB I/O on the same event loop as FastAPI, with typed `Mapped[...]` models. Relationships use `lazy="raise"` so an accidental async lazy-load fails loudly instead of erroring at random. |
| Database | PostgreSQL 17 | Native enum types, FK actions (`SET NULL` / `RESTRICT`), composite indexes. |
| Migrations | Alembic | Versioned, reversible schema changes. A constraint naming convention on `Base.metadata` keeps generated names deterministic. |
| Validation / settings | Pydantic v2 + pydantic-settings | Strict request models. Typed configuration from environment variables or `.env`. |
| Password hashing | pwdlib[bcrypt] | Used instead of passlib, which is unmaintained and breaks with `bcrypt >= 4.1` (it reads a removed `__about__` attribute). pwdlib is a small, maintained replacement. |
| JWT | PyJWT | Small and maintained. Validates `exp` and required claims. Used instead of python-jose, which is largely unmaintained. |
| Tests | pytest + pytest-asyncio + httpx `AsyncClient` | Runs the real app against a real PostgreSQL test database. |
| Lint / format | Ruff | One fast tool for linting, import sorting and formatting. |
| Packaging | Docker + Docker Compose | One command brings up the DB, API (migrations and seed included) and dashboard. |

---

## Quick start (Docker)

Prerequisite: Docker with the Compose plugin.

```bash
git clone <repo-url>
cd task-management-system-with-rbac
cp .env.example .env
# Edit .env: set SECRET_KEY (at least 32 chars). Generate one with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d --build
```

On startup the API container runs `alembic upgrade head` and then `python -m scripts.seed_admin` before it starts uvicorn. The first admin is created from `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` (default `admin@example.com` / `Admin12345`).

| Service | URL / host port | Notes |
|---|---|---|
| API | http://localhost:18000 | Swagger `/docs`, ReDoc `/redoc`, OpenAPI `/openapi.json`, `GET /health` |
| Frontend (nginx) | http://localhost:18080 | Serves `frontend/` and proxies API paths to the API container |
| PostgreSQL | `localhost:15432` | Data persists in a named volume |

The host ports avoid the usual defaults (8000 / 5432 / 80), which are often already in use. You can change them with `API_HOST_PORT`, `DB_HOST_PORT` and `FRONTEND_HOST_PORT` in `.env`. The container ports stay 8000 / 5432 / 80.

Useful commands:

```bash
docker compose ps                          # service status
docker compose logs -f                     # follow logs
docker compose --profile test run --rm test   # run the test suite in a container
docker compose down                        # stop (keeps data)
docker compose down -v                     # stop and delete the database volume
```

### Trying it in Swagger UI

1. Open http://localhost:18000/docs.
2. Click **Authorize**. Enter your **email in the `username` field** and your password, for example the seeded admin. Swagger calls `POST /auth/login` for you.
3. Call any endpoint. The token is kept across page reloads (`persistAuthorization` is enabled).

---

## Local development (without Docker for the API)

Prerequisites: Python 3.12+, and Docker for PostgreSQL (or any reachable PostgreSQL instance).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env                 # set SECRET_KEY
docker compose up -d db              # start only PostgreSQL (host port 15432)

# .env already points at the local DB:
# DATABASE_URL=postgresql+asyncpg://task_user:task_password@localhost:15432/task_db

alembic upgrade head                 # create the schema and seed the roles
python -m scripts.seed_admin         # create the first ADMIN (idempotent)
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

---

## Configuration

Settings are read from environment variables, and from `.env` when present (`app/core/config.py`, pydantic-settings, case-insensitive). Every variable in [.env.example](.env.example):

| Variable | Default in `.env.example` | Used by | Description |
|---|---|---|---|
| `ENVIRONMENT` | `local` | API | One of `local`, `test`, `production`. |
| `SECRET_KEY` | `change-me-...` | API | HMAC key for signing JWTs. **Required**, at least 32 characters (PyJWT warns below 32 bytes for HS256). Replace it with a random value. |
| `JWT_ALGORITHM` | `HS256` | API | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | API | Access token lifetime in minutes (≥ 1). Login returns it as `expires_in`, in seconds. |
| `CORS_ORIGINS` | *(empty)* | API | Comma-separated (or JSON list) allowed origins. Empty disables the CORS middleware. The bundled dashboard doesn't need CORS because nginx proxies it on the same origin. |
| `POSTGRES_USER` | `task_user` | db container | PostgreSQL user created by the `postgres` image. |
| `POSTGRES_PASSWORD` | `task_password` | db container | Password for that user. |
| `POSTGRES_DB` | `task_db` | db container | Database created on first start. |
| `DATABASE_URL` | `postgresql+asyncpg://task_user:task_password@localhost:15432/task_db` | API, Alembic, seed | SQLAlchemy URL. A plain `postgresql://` URL is upgraded to `postgresql+asyncpg://` automatically. Inside Compose the host is `db:5432`. |
| `FIRST_ADMIN_EMAIL` | `admin@example.com` | `scripts/seed_admin.py` | Email of the bootstrap ADMIN. |
| `FIRST_ADMIN_PASSWORD` | `Admin12345` | `scripts/seed_admin.py` | Password of the bootstrap ADMIN. Change it for any shared deployment. |
| `API_HOST_PORT` | `18000` | Compose | Host port mapped to the API container's port 8000. |
| `DB_HOST_PORT` | `15432` | Compose | Host port mapped to PostgreSQL's port 5432. |
| `FRONTEND_HOST_PORT` | `18080` | Compose | Host port mapped to nginx's port 80. |

Optional settings that are not in `.env.example`: `DB_ECHO` (log SQL, default `false`), `DB_POOL_SIZE` (default `5`), `DB_MAX_OVERFLOW` (default `10`). For tests, `TEST_DATABASE_URL` (see [Testing](#testing-and-linting)).

---

## Project structure

```text
app/
├── api/
│   ├── deps.py            # get_db, get_current_user, require_roles(...)
│   ├── router.py          # mounts the auth, tasks and users routers
│   └── routes/
│       ├── auth.py        # POST /auth/register, POST /auth/login
│       ├── tasks.py       # /tasks CRUD, assign, status
│       └── users.py       # GET /users/me, GET /users
├── core/
│   ├── config.py          # Settings (pydantic-settings)
│   ├── security.py        # bcrypt (pwdlib) + JWT encode/decode (PyJWT)
│   └── exceptions.py      # AppException hierarchy + global exception handlers
├── db/
│   ├── base.py            # DeclarativeBase with a constraint naming convention
│   └── session.py         # async engine + async_sessionmaker
├── models/                # Role, User, Task, enums (RoleName, TaskStatus)
├── schemas/               # Pydantic request/response models, Page[T], ErrorResponse
├── services/              # Business logic, RBAC checks, queries, transactions
│   ├── auth_service.py
│   ├── task_service.py
│   └── user_service.py
└── main.py                # create_app(): middleware, handlers, routers, /health
alembic/                   # env.py (async) + versions/ (0001 schema, 0002 roles)
scripts/seed_admin.py      # idempotent first-ADMIN bootstrap
tests/                     # pytest suite (real PostgreSQL)
frontend/                  # vanilla JS dashboard (no build step)
nginx/default.conf         # serves frontend/, proxies API paths to the API
docs/                      # ERD.md, postman_collection.json
Dockerfile, docker-compose.yml, .env.example, alembic.ini, pyproject.toml
```

---

## Architecture

### Layers

| Layer | Responsibility | Rules it follows |
|---|---|---|
| `app/api` | HTTP only: parse input, declare dependencies, call one service function, return a schema, set the status code. | No queries or business rules. `deps.py` holds the reusable dependencies: `get_db` (one `AsyncSession` per request, rolled back on error), `get_current_user` (bearer token → `User`, otherwise 401), `require_roles(*roles)` (403 if the role isn't allowed). |
| `app/services` | All business logic: permission checks, status transitions, assignee validation, visibility-filtered queries, commits. | Raise domain exceptions (`PermissionDeniedError`, `NotFoundError`, ...) and **never** `HTTPException`, so the logic doesn't depend on the web layer. Services own their transactions (`commit` / `refresh`). |
| `app/core` | Cross-cutting concerns. | `config` (typed settings), `security` (pure functions with no DB access: hash/verify, create/decode token; unknown-email logins still run a bcrypt verify against a dummy hash so timing doesn't reveal which accounts exist), `exceptions` (the `AppException` hierarchy and the global handlers that render the error format). |
| `app/db` | Engine and session factory. `Base` with a naming convention (`pk_%(table)s`, `fk_%(table)s_%(col)s_%(ref)s`, ...). | `expire_on_commit=False`, because async code can't lazily refresh expired attributes. |
| `app/models` | SQLAlchemy 2.0 typed models. | `User.role` is loaded eagerly (`lazy="joined"`) because every request needs it. Other relationships use `lazy="raise"`. |
| `app/schemas` | Pydantic v2 contracts. | Request models inherit `RequestSchema` (`extra="forbid"`, whitespace stripped). Responses are built from ORM objects (`from_attributes=True`). |
| `app/main.py` | `create_app()` factory. | Registers exception handlers, optional CORS, routers and `/health`. Disposes the engine on shutdown. |

### Request flow

```mermaid
sequenceDiagram
    participant C as Client
    participant R as Route (app/api/routes)
    participant D as Dependencies (deps.py)
    participant S as Service (app/services)
    participant DB as PostgreSQL

    C->>R: PATCH /tasks/7/status  (Bearer token)
    R->>D: get_db, get_current_user
    D->>D: decode JWT (401 if missing/invalid/expired)
    D->>DB: load user + role (401 if user gone)
    R->>D: require_roles(...) if the route is role-gated (403)
    R->>S: update_status(db, user, task_id, payload)
    S->>DB: SELECT task
    S->>S: 404 if missing, 403 if outside caller's scope,<br/>400 if transition invalid
    S->>DB: UPDATE + COMMIT
    S-->>R: Task
    R-->>C: 200 TaskRead (schema)
```

Any `AppException` raised along the way goes to the global handler and comes back in the standard [error format](#error-format).

### Defense in depth for RBAC

1. **Route gate.** `Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER))` rejects roles that may never perform the action (for example a USER calling `POST /tasks` or `DELETE /tasks/{id}`). The guard is declarative and shows up in the route signature.
2. **Service check.** The service repeats the complete rule, including the parts a role gate can't express ("a MANAGER may only assign tasks they created or are assigned to", "a USER may only update the status of tasks assigned to them"). A service called from somewhere other than a route (a script, a future endpoint, a test) is still safe.
3. **SQL visibility filter.** List and detail reads add a `WHERE` clause based on the caller's role (`created_by = :me OR assigned_to = :me` for MANAGER, `assigned_to = :me` for USER), so rows the caller can't see are never loaded. Pagination counts are correct too: `total` counts visible rows only.

---

## Roles and permissions

"Own" for a MANAGER means **created by them or assigned to them**.

| Action | Endpoint | ADMIN | MANAGER | USER |
|---|---|:---:|:---:|:---:|
| Create task | `POST /tasks` | ✅ | ✅ | ❌ |
| List tasks | `GET /tasks` | ✅ all | ✅ created or assigned | ✅ assigned only |
| View one task | `GET /tasks/{id}` | ✅ all | ✅ created or assigned | ✅ assigned only |
| Assign / unassign | `PATCH /tasks/{id}/assign` | ✅ any task | ✅ own tasks | ❌ |
| Update status | `PATCH /tasks/{id}/status` | ✅ any task | ✅ own tasks | ✅ assigned only |
| Delete task | `DELETE /tasks/{id}` | ✅ | ❌ | ❌ |
| List users | `GET /users` | ✅ | ✅ | ❌ |
| Current user | `GET /users/me` | ✅ | ✅ | ✅ |

Which response a denied request gets:

| Situation | Response |
|---|---|
| No token, malformed token, expired token, or the user was deleted | `401 UNAUTHORIZED` |
| The role can never perform the action (route gate) | `403 FORBIDDEN`. This happens **before** the existence check. |
| The role may perform the action, but the task exists outside the caller's scope | `403 FORBIDDEN` |
| The task doesn't exist | `404 NOT_FOUND` |

---

## Task status workflow

Transitions are validated in the service against an explicit map:

```mermaid
stateDiagram-v2
    [*] --> PENDING : created
    PENDING --> IN_PROGRESS
    PENDING --> COMPLETED
    IN_PROGRESS --> PENDING
    IN_PROGRESS --> COMPLETED
    COMPLETED --> IN_PROGRESS : reopen
```

| From \ To | PENDING | IN_PROGRESS | COMPLETED |
|---|:---:|:---:|:---:|
| **PENDING** | ❌ same | ✅ | ✅ |
| **IN_PROGRESS** | ✅ | ❌ same | ✅ |
| **COMPLETED** | ❌ **never** | ✅ reopen | ❌ same |

A disallowed or same-status transition returns `400 INVALID_STATUS_TRANSITION`. An unknown status value (for example `"DONE"`) fails schema validation with `422 VALIDATION_ERROR`.

---

## Assumptions and design decisions

The brief leaves some behaviour open. These are the choices made, with the reasoning:

1. **MANAGER scope.** A MANAGER can assign, and update the status of, only tasks they **created or are assigned to**. This matches what they can see ("Created/Assigned" in the brief). ADMIN can act on any task.
2. **403 vs 404 for out-of-scope tasks.** When a task exists but is outside the caller's scope, the API returns **403**. 404 is used only when the task doesn't exist. The brief defines 403 as "authenticated but not allowed", and an explicit 403 is easier to reason about and test. (The trade-off: a caller can tell that a task ID exists.)
3. **Role gate before the existence check.** Route-level role checks run first, so a USER calling `DELETE /tasks/999999` gets **403**, not 404. That user may not delete any task, whether or not it exists.
4. **Registration always creates a USER.** The register body accepts only `email` and `password`. Extra fields such as `role` are **rejected with 422** (`extra="forbid"`) rather than silently ignored, so privilege escalation is impossible and the mistake is visible to the caller.
5. **Bootstrapping the first ADMIN.** `scripts/seed_admin.py` creates an ADMIN from `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` if none exists. It runs automatically on container start and is idempotent. There is no endpoint for changing roles. Promote users to MANAGER in the database if needed (for example `UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'MANAGER') WHERE email = '...'`).
6. **Who can be an assignee.** ADMINs and MANAGERs can assign a task to **any existing user**, whatever that user's role. An assignee ID that doesn't exist returns **422 `ASSIGNEE_NOT_FOUND`**: the request is well-formed but semantically invalid, and the task itself was found. `assigned_to: null` unassigns. Creation also accepts an optional `assigned_to`.
7. **Due dates.** `due_date` is a calendar `date` (no time or timezone) and may be omitted. It **cannot be in the past at creation** (422).
8. **Emails are case-insensitive.** They are lower-cased by the schema before storage and lookup, so a plain `UNIQUE` index enforces case-insensitive uniqueness. Registering a duplicate returns **409 `EMAIL_ALREADY_REGISTERED`**.
9. **Password policy.** 8–72 **bytes**, with at least one letter and one digit. The 72-byte limit is bcrypt's input limit. Longer passwords are rejected instead of being silently truncated.
10. **Deleting a user.** A deleted assignee sets the task's `assigned_to` to `NULL` (`ON DELETE SET NULL`). A creator can't be deleted while they own tasks (`ON DELETE RESTRICT`), which preserves the audit trail.
11. **No refresh tokens.** Access tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 60) and the client logs in again when one expires. This keeps the auth surface small for the scope of the assessment.
12. **Reopening is allowed.** `COMPLETED → IN_PROGRESS` is permitted so finished work can be reopened. The brief only forbids `COMPLETED → PENDING`, which is always rejected.
13. **Login uses the OAuth2 password form** (`application/x-www-form-urlencoded`, `username` = email). This makes Swagger's **Authorize** button work without any customisation.
14. **Invalid credentials.** Unknown email and wrong password both return the same `401 INVALID_CREDENTIALS`, so the response doesn't reveal which accounts exist.

---

## Error format

Every error response has the same body:

```json
{
  "error": {
    "code": "INVALID_STATUS_TRANSITION",
    "message": "Cannot change status from COMPLETED to PENDING",
    "details": {"from": "COMPLETED", "to": "PENDING", "allowed": ["IN_PROGRESS"]}
  }
}
```

For validation errors, `details` lists the failing fields:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {"field": "body.password", "message": "Value error, Password must contain at least one letter and one digit", "type": "value_error"}
    ]
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `INVALID_STATUS_TRANSITION` | Transition not in the allowed map, or same status |
| 401 | `UNAUTHORIZED` | Missing, invalid or expired token, or the user no longer exists (sent with `WWW-Authenticate: Bearer`) |
| 401 | `INVALID_CREDENTIALS` | Wrong email or password at login |
| 403 | `FORBIDDEN` | Role not allowed, or the task is outside the caller's scope |
| 404 | `NOT_FOUND` | Task doesn't exist, or unknown route |
| 409 | `EMAIL_ALREADY_REGISTERED` | Registering an email that is already taken |
| 422 | `VALIDATION_ERROR` | Schema validation failed (bad types, unknown fields, weak password, past due date, ...) |
| 422 | `ASSIGNEE_NOT_FOUND` | `assigned_to` refers to a user that doesn't exist |
| 500 | `INTERNAL_ERROR` | Unhandled exception. It is logged server-side, and no internals are leaked to the client. |

Errors raised by the framework itself use the HTTP reason phrase as the code, for example `METHOD_NOT_ALLOWED` (405).

---

## API reference and curl examples

| Method | Path | Auth | Success | Body / query |
|---|---|---|---|---|
| `POST` | `/auth/register` | none | `201` user | JSON `{email, password}` |
| `POST` | `/auth/login` | none | `200` token | form `username=<email>&password=...` |
| `GET` | `/users/me` | any role | `200` user | |
| `GET` | `/users` | ADMIN, MANAGER | `200` page of users | `?page=1&size=20` |
| `POST` | `/tasks` | ADMIN, MANAGER | `201` task | JSON `{title, description?, due_date?, assigned_to?}` |
| `GET` | `/tasks` | any role | `200` page of tasks | `?page=1&size=20&status=PENDING` |
| `GET` | `/tasks/{id}` | any role (visibility) | `200` task | |
| `PATCH` | `/tasks/{id}/assign` | ADMIN, MANAGER (own) | `200` task | JSON `{assigned_to: int \| null}` |
| `PATCH` | `/tasks/{id}/status` | all (scoped) | `200` task | JSON `{status}` |
| `DELETE` | `/tasks/{id}` | ADMIN | `204` | |
| `GET` | `/health` | none | `200` `{"status": "ok"}` | |

Pagination: `page` ≥ 1 (default 1), `size` 1–100 (default 20). Tasks are returned newest first. Page responses have the shape `{"items": [...], "total": 42, "page": 1, "size": 20, "pages": 3}`.

The examples below use the Docker port. Set `BASE` once:

```bash
BASE=http://localhost:18000
```

### Auth

```bash
# Register (always creates a USER)
curl -s -X POST $BASE/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email": "alice@example.com", "password": "Secret123"}'
# 201
# {"id": 2, "email": "alice@example.com", "role": "USER", "created_at": "2026-10-17T09:00:00Z"}

# Log in as the seeded admin. Form-encoded; the username field holds the email.
curl -s -X POST $BASE/auth/login \
  -d 'username=admin@example.com&password=Admin12345'
# {"access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 3600}

# Capture the token (requires jq)
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -d 'username=admin@example.com&password=Admin12345' | jq -r .access_token)
# Without jq: copy access_token from the response and run TOKEN=eyJhbGciOi...
```

### Users

```bash
curl -s $BASE/users/me -H "Authorization: Bearer $TOKEN"
# {"id": 1, "email": "admin@example.com", "role": "ADMIN", "created_at": "..."}

curl -s "$BASE/users?page=1&size=20" -H "Authorization: Bearer $TOKEN"
# {"items": [{"id": 1, ...}, {"id": 2, ...}], "total": 2, "page": 1, "size": 20, "pages": 1}
```

### Tasks

```bash
# Create (ADMIN/MANAGER). description, due_date and assigned_to are optional.
curl -s -X POST $BASE/tasks \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title": "Write report", "description": "Q3 numbers", "due_date": "2026-12-31", "assigned_to": 2}'
# 201
# {"id": 1, "title": "Write report", "description": "Q3 numbers", "status": "PENDING",
#  "due_date": "2026-12-31", "assigned_to": 2, "created_by": 1,
#  "created_at": "...", "updated_at": "..."}

# List visible tasks, optionally filtered by status
curl -s "$BASE/tasks?page=1&size=20&status=PENDING" -H "Authorization: Bearer $TOKEN"
# {"items": [ ... ], "total": 1, "page": 1, "size": 20, "pages": 1}

# Get one
curl -s $BASE/tasks/1 -H "Authorization: Bearer $TOKEN"

# Assign (or unassign with null)
curl -s -X PATCH $BASE/tasks/1/assign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"assigned_to": 2}'
curl -s -X PATCH $BASE/tasks/1/assign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"assigned_to": null}'

# Update status
curl -s -X PATCH $BASE/tasks/1/status \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status": "IN_PROGRESS"}'

# Delete (ADMIN only)
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE $BASE/tasks/1 \
  -H "Authorization: Bearer $TOKEN"
# 204
```

### Health

```bash
curl -s $BASE/health
# {"status": "ok"}
```

### Example error responses

```bash
# No token
curl -s $BASE/tasks
# 401 {"error": {"code": "UNAUTHORIZED", "message": "Not authenticated", "details": null}}

# COMPLETED -> PENDING is never allowed
curl -s -X PATCH $BASE/tasks/1/status \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status": "PENDING"}'
# 400 {"error": {"code": "INVALID_STATUS_TRANSITION",
#      "message": "Cannot change status from COMPLETED to PENDING",
#      "details": {"from": "COMPLETED", "to": "PENDING", "allowed": ["IN_PROGRESS"]}}}

# Trying to register with a role
curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' \
  -d '{"email": "eve@example.com", "password": "Secret123", "role": "ADMIN"}'
# 422 {"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed",
#      "details": [{"field": "body.role", "message": "Extra inputs are not permitted", "type": "extra_forbidden"}]}}
```

Error messages are shown as examples. The `code` values are the stable contract.

---

## Database and migrations

Schema overview (full diagram, types and rationale in **[docs/ERD.md](docs/ERD.md)**):

- `roles` (`id`, `name` enum `ADMIN`/`MANAGER`/`USER`, unique)
- `users` (`id`, `email` unique, `hashed_password`, `role_id` → `roles` `RESTRICT`, `created_at`)
- `tasks` (`id`, `title`, `description`, `status` enum, `due_date`, `assigned_to` → `users` `SET NULL`, `created_by` → `users` `RESTRICT`, `created_at`, `updated_at`)

Migrations live in `alembic/versions/`:

| Revision | Content |
|---|---|
| `0001` | Initial schema: enums, the three tables, FKs and indexes |
| `0002` | Seeds the three roles (data migration, so every environment gets the same role rows) |

Common commands (run from the project root, with `DATABASE_URL` set):

```bash
alembic upgrade head                               # apply all migrations
alembic downgrade -1                               # roll back one revision
alembic downgrade base                             # roll back everything
alembic current                                    # show the current revision
alembic history                                    # list revisions
alembic revision --autogenerate -m "add x to y"    # new revision from model changes (review it!)
```

In Docker, prefix the commands with `docker compose exec api`. Migrations run automatically on every API container start.

---

## Testing and linting

The suite runs against a **real PostgreSQL** database, so enums, FK actions and constraints behave exactly as they do in production. The conftest creates the test database itself if it doesn't exist.

```bash
# In Docker (runs pytest in a throwaway container against the compose db)
docker compose --profile test run --rm test

# Locally (db container running on 15432)
docker compose up -d db
pytest                       # or: pytest -v, pytest tests/test_tasks.py -k status
```

`TEST_DATABASE_URL` sets the test DB. The default is `postgresql+asyncpg://task_user:task_password@localhost:15432/task_db_test`. It is kept separate from the dev database so tests never touch your data.

The suite targets the graded behaviour: registration and login rules, token handling, the RBAC matrix, visibility filtering and pagination, assignment rules, status transitions and the error format.

Lint and format checks:

```bash
ruff check . && ruff format --check .
```

---

## Postman collection

[docs/postman_collection.json](docs/postman_collection.json) (Postman v2.1):

1. In Postman, choose **Import** and select the file.
2. Collection variables: `base_url` (default `http://localhost:18000`), `token`, `task_id`, `user_id`.
3. Run **Auth → Login**. Its test script stores the access token in `token`, and every other request inherits collection-level Bearer auth using `{{token}}`.
4. Run **Tasks → Create task**. Its test script stores the new id in `task_id`, which the other task requests use.

The folders are Auth, Users, Tasks and Health. They include negative examples such as a request with no token, an invalid status transition and registration with a `role` field.

---

## Frontend

`frontend/` contains a small dashboard written in plain HTML, CSS and JavaScript, with no build step. It is served by the `frontend` nginx container at http://localhost:18080. nginx also proxies the API paths (`/auth`, `/tasks`, `/users`) to the API container (`nginx/default.conf`), so the browser talks to a single origin and CORS isn't needed.

The UI hides actions the current role can't perform, but it is only a convenience. Every rule is enforced by the API.
