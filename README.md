# Task Management API with RBAC

A FastAPI backend for managing tasks with role-based access control. Admins, managers and users each get a different set of permissions, enforced in a dedicated service layer. PostgreSQL stores the data, Redis caches list endpoints, and a Celery worker handles background jobs.

![Python](https://img.shields.io/badge/Python_3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis_8-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-373737?style=for-the-badge&logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)

[Postman collection](https://documenter.getpostman.com/view/32993281/2sBXwntrnU#77d965fe-1678-44f8-ba80-33b71e04e17a)

---

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Frontend](#frontend)
- [Using the API](#using-the-api)
- [Roles and permissions](#roles-and-permissions)
- [Architecture](#architecture)
- [Running tests](#running-tests)
- [Project structure](#project-structure)
- [Known issues](#known-issues)

---

## Features

- **JWT authentication** with access tokens (30 min) and refresh tokens (7 days). Passwords are hashed with bcrypt.
- **Three roles** (`ADMIN`, `MANAGER`, `USER`), with permission checks in the service layer rather than in route handlers.
- **Task status workflow**: `PENDING → IN_PROGRESS → COMPLETED`. A completed task cannot be moved back.
- **Pagination, search and filtering** on the task and user lists (`limit`, `skip`, `search`, `status`).
- **Redis caching** on list endpoints through a `@cache_response` decorator.
- **Background jobs**: sign-up queues a welcome email on a Celery worker, so the request returns immediately.
- **Database migrations** with Alembic. These run automatically when the API container starts, along with seeding the three roles.
- **Custom Swagger UI** at `/docs`.
- **Web dashboard** in plain HTML, CSS and JavaScript, with the UI adapted to each role.

---

## Quick start

You need Docker with the Compose plugin.

```bash
git clone <repo-url>
cd task-management-system-with-rbac
cp .env.example .env          # then set SECRET_KEY to a long random string
docker compose up --build -d
```

When the containers are up, open the dashboard at **http://localhost:18080**, or the API docs at **http://localhost:18000/docs**.

| Service | Host port | Notes |
|---|---|---|
| Frontend (nginx) | `18080` | Dashboard UI; also proxies API calls to the `web` service |
| API | `18000` | Swagger UI at `/docs`, OpenAPI schema at `/openapi.json` |
| PostgreSQL 17 | `15432` | Data is stored in the `pg17_data` volume |
| Redis 8 | `16379` | Cache and Celery broker |
| Celery worker | — | Has no exposed port; it takes jobs from Redis |

The host ports deliberately avoid the defaults (8000, 5432, 6379) so the stack can run alongside other projects. You can change them in `.env`.

Common commands:

```bash
docker compose ps                     # service status
docker compose logs -f web            # API logs
docker compose logs -f celery_worker  # worker logs
docker compose down                   # stop (data is kept)
docker compose down -v                # stop and delete the database volume
```

The API container mounts `./app` and runs with `--reload`, so code changes apply without a rebuild. Rebuild after changing `requirements.txt`.

---

## Configuration

All settings are read from `.env`. Compose passes the file to the API and worker containers.

| Variable | Default in `.env.example` | Purpose |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `admin_user` / `super_secret_password` / `task_db` | Credentials the Postgres container is created with |
| `DATABASE_URL` | `postgresql://admin_user:super_secret_password@db:5432/task_db` | SQLAlchemy connection string (uses the psycopg 3 driver) |
| `SECRET_KEY` | `replace_with_secure_key` | Key for signing JWTs. **Always change it.** If it's missing, the app falls back to an insecure default. |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Redis used by Celery and by the response cache |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Where Celery stores task results |
| `API_HOST_PORT` / `DB_HOST_PORT` / `REDIS_HOST_PORT` / `FRONTEND_HOST_PORT` | `18000` / `15432` / `16379` / `18080` | Ports published on the host |

Inside the Docker network, services reach each other by service name (`db:5432`, `redis:6379`). The host ports above are only for access from your machine. For example, to connect a database client:

```text
postgresql://admin_user:super_secret_password@localhost:15432/task_db
```

---

## Frontend

A small dashboard in `frontend/`, written in plain HTML, CSS and JavaScript with Lucide icons. There is no build step.

| Page | What it does |
|---|---|
| `login.html` / `signup.html` | Sign in or register. Tokens are stored in `localStorage`. |
| Dashboard | Task counts by status and the five most recent tasks |
| Tasks | Search, status filter, pagination, a status dropdown per row, and dialogs to create, assign and delete tasks |
| Users (admin) | User list with search and role badges |
| Roles (admin) | The three roles and a permission comparison |

Buttons the current role can't use are hidden, but the API still enforces every rule. When the access token expires, the app silently gets a new one with the refresh token. If that also fails, it returns to the sign-in page.

**How it reaches the API.** The `frontend` service (nginx) serves the files and forwards `/auth`, `/tasks`, `/users` and `/roles` to FastAPI, so the browser only ever talks to one origin. This matters because the API doesn't send CORS headers: a page on another origin calling `:18000` directly would be blocked. The proxy config is in `nginx/default.conf`.

**Limitations that come from the API:**
- Tasks only include user IDs, and only admins can list users. Admins therefore see assignee emails, while managers see "You" or "User #id" and assign tasks by entering a user ID.
- Tasks have no creation date, so "Recent tasks" means the tasks with the highest IDs.
- Because of the cache issues described under [Known issues](#known-issues), a new or changed task can take up to 60 seconds to appear in lists.

---

## Using the API

### First steps

1. **Sign up.** Call `POST /auth/signup`. Role IDs are seeded as `1 = ADMIN`, `2 = MANAGER`, `3 = USER`.
   ```json
   { "email": "admin@example.com", "password": "Passw0rd!", "role_id": 1 }
   ```
2. **Authorise.** Copy the `access_token` from the response, click **Authorize** in Swagger, and paste it in.
3. **Create a task** as an admin or manager, assign it to a user, then move it through the workflow as that user.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/signup` | Register. Returns tokens and the user, and queues a welcome email |
| `POST` | `/auth/login` | Exchange email and password for access and refresh tokens |
| `POST` | `/auth/refresh` | Exchange a refresh token for a new pair of tokens |
| `GET` | `/tasks/` | List tasks visible to the caller. Supports `limit`, `skip`, `search` and `status` |
| `POST` | `/tasks/` | Create a task, optionally with `assigned_to_id` and a future `due_date` |
| `PATCH` | `/tasks/{id}/assign` | Assign a task: `{ "assign_to_id": 3 }` |
| `PATCH` | `/tasks/{id}/status` | Change status: `{ "status": "IN_PROGRESS" }` |
| `DELETE` | `/tasks/{id}` | Delete a task |
| `GET` | `/users/` | List users. Supports `limit`, `skip` and `search` (email) |
| `GET` | `/roles/` | List roles |

### Status codes

| Code | When it's returned |
|---|---|
| `201` | User created |
| `400` | Duplicate email, or a disallowed status change |
| `401` | Missing, invalid or expired token, or wrong credentials |
| `403` | The caller's role isn't allowed to perform the action |
| `404` | The task, user or role doesn't exist |
| `422` | The request body failed validation (for example, a `due_date` in the past) |

---

## Roles and permissions

| Action | `ADMIN` | `MANAGER` | `USER` |
|---|:---:|:---:|:---:|
| Create tasks | ✅ | ✅ | ❌ |
| View tasks | ✅ all | ✅ created by or assigned to them | ✅ assigned to them |
| Assign tasks | ✅ | ✅ | ❌ |
| Update task status | ✅ | ✅ created by or assigned to them | ✅ assigned to them |
| Delete tasks | ✅ | ❌ | ❌ |
| List users | ✅ | ❌ | ❌ |
| List roles | ✅ | ❌ | ❌ |

All checks are in `app/services/*`. Routes only resolve the current user (`Depends(get_current_user)`) and pass it to the service.

**Status rule:** once a task is `COMPLETED`, it can't move to any other status.

---

## Architecture

<img width="1536" height="886" alt="System architecture diagram" src="https://github.com/user-attachments/assets/5e960796-4f71-4f7f-8da5-d9175a16f2ea" />

- **FastAPI (`web`)** handles HTTP, validation and authentication. Database access is synchronous (SQLAlchemy 2.1 with psycopg 3), and FastAPI runs those handlers in its threadpool.
- **PostgreSQL** is the source of truth for users, roles and tasks. The schema is managed by Alembic.
- **Redis** has two jobs: it caches list responses, and it acts as the Celery broker and result backend.
- **Celery (`celery_worker`)** runs slow work outside the request. Right now that is a simulated welcome email (`app/tasks/email_tasks.py`).

On startup, `entrypoint.sh` runs `alembic upgrade head` and `seed.py`, but only when `RUN_MIGRATIONS=1`. Only the API service sets it, so the worker never runs migrations at the same time.

### Data model

<img width="1368" height="371" alt="ER diagram" src="https://github.com/user-attachments/assets/5eecea40-c968-4f84-95fe-cea0d6f6cb1c" />

- `roles`: `id`, `name` (enum `ADMIN | MANAGER | USER`)
- `users`: `id`, `email` (unique), `hashed_password`, `role_id → roles.id`
- `tasks`: `id`, `title`, `description`, `status` (enum), `due_date`, `assigned_to_id → users.id` (set to null when the user is deleted), `created_by_id → users.id` (the task is deleted with its creator)

---

## Running tests

The suite (75 tests) uses an in-memory SQLite database and FastAPI's `TestClient`, so it doesn't touch the Postgres data.

```bash
# inside the running stack
docker compose exec web pytest -q

# or in a throwaway container
docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 web pytest -q
```

| File | What it covers |
|---|---|
| `tests/test_auth.py` | Sign-up, login, refresh, token validation |
| `tests/test_roles.py` | Role listing and admin-only access |
| `tests/test_users.py` | User listing, pagination, search, permissions |
| `tests/test_tasks.py` | Task creation, visibility per role, assignment, status workflow, deletion |

**Current result: 72 passed, 3 failed, 22 errors.** All the failures and errors come from the caching bug described under [Known issues](#known-issues).

### Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

To run the API itself outside Docker, point `DATABASE_URL` and `CELERY_BROKER_URL` in `.env` at `localhost:15432` and `localhost:16379`. Then run `alembic upgrade head` and `uvicorn app.main:app --reload`.

---

## Project structure

```text
app/
├── api/         # Routers: auth, tasks, users, roles
├── core/        # JWT/bcrypt, auth dependency, Redis client, cache decorator, Celery app, Swagger setup
├── db/          # Engine, session factory, declarative base
├── models/      # SQLAlchemy models: Role, User, Task
├── schemas/     # Pydantic request/response models
├── services/    # Business logic and permission checks
├── tasks/       # Celery tasks
└── main.py      # App factory and lifespan (Redis pool)
frontend/        # Static dashboard (HTML, CSS, vanilla JS)
nginx/           # nginx config: serves frontend/ and proxies the API
alembic/         # Migration environment and versions
tests/           # Pytest suite
seed.py          # Inserts the three roles if missing
entrypoint.sh    # Runs migrations and seeding, then starts the given command
```

---

## Known issues

These are known bugs that haven't been fixed yet:

- **Cache responses are shared across users.** The key in `app/core/decorators.py` is built from query parameters only, not from who is calling. A cached admin response to `GET /users/` or `GET /tasks/` can therefore be returned to other users, which bypasses the role checks.
- **The cache is never cleared on writes.** Creating, assigning, updating or deleting a task doesn't remove cached lists, so they stay stale for up to 60 seconds (5 minutes for users).
- **The cache decorator uses the wrong event loop.** It runs async Redis calls on a new event loop inside a worker thread, using a connection pool created on the main loop. Under load, and in the test suite, this fails with `attached to a different loop`.
- **Sign-up accepts any role.** `POST /auth/signup` lets the caller choose `role_id`, so anyone can register as an admin. New users should get `USER`, and only admins should be able to grant roles.
- **Statuses can be skipped.** A task can go straight from `PENDING` to `COMPLETED`, because only moves out of `COMPLETED` are blocked. The error message for that case always mentions "Pending", whichever status was requested.
- **Unused config file.** `app/core/config.py` defines a `JWT_SECRET_KEY` setting that nothing imports. The key actually used is `SECRET_KEY`, in `app/core/security.py`.
