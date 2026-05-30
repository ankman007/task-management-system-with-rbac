## Task Management System API with RBAC

### Project Overview 
Task Management API System with Role-Based Access Control (RBAC) built in Python with FastAPI, PostgreSQL, SQLAlchemy 2.0 (synchronous), Alembic, Docker, and Docker Compose.

### Project architecture
```text
app/
├── api/       # Routes / Endpoints
├── core/      # Security (JWT, Hashing), Config
├── db/        # Session setup, Base model
├── models/    # SQLAlchemy models
├── schemas/   # Pydantic validation models
├── services/  # Business logic (DB queries, RBAC checks)
└── main.py    # FastAPI app initialization
```

### Implemented requirements
  - JWT authentication with access + refresh tokens.
  - Granular RBAC for `ADMIN`, `MANAGER`, and `USER`.
  - Task workflow enforcing strict transitions: `PENDING -> IN_PROGRESS -> COMPLETED` and blocking completed-to-pending rollback.
  - Docker Compose orchestration for API, PostgreSQL, Redis, and Celery worker.
  - Cursor/offset pagination and multi-parameter filtering/search for users and tasks.
  - Interactive custom Swagger/OpenAPI UI at `/docs`.
  - Redis caching decorators for repeated search/page hits.
  - Asynchronous Celery email worker pipeline for background notification simulation.

### Omitted requirement 
- Asynchronous database handling. The implementation uses synchronous SQLAlchemy + `psycopg2` with synchronous DB transactions.

## Architecture & Approach
- The system uses separation of concerns:
  - `app/api/*` defines HTTP routers and request validation.
  - `app/services/*` contains domain/business logic and permission enforcement.
  - `app/models/*` defines SQLAlchemy ORM entities.
  - `app/schemas/*` defines Pydantic request/response contracts.
  - `app/core/*` handles configuration, security, Redis caching, Celery, and Swagger customization.
- Design rationale:
  - Synchronous DB access keeps the API footprint lean and avoids added complexity from async drivers like `asyncpg`.
  - Redis caching is layered independently to accelerate read-heavy endpoints without changing the DB model.
  - Celery is isolated as a worker service for expensive or delayed operations (simulated email notifications), so API responsiveness is preserved.

## Security & RBAC Implementation Matrix
| Role | View all users | View/Create tasks | Assign tasks | Update task status | Delete tasks | Status workflow enforcement |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `ADMIN` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `MANAGER` | ❌ | ✅ | ✅ | ✅ (own or assigned tasks only) | ❌ | ✅ |
| `USER` | ❌ | ❌ | ❌ | ✅ (assigned tasks only) | ❌ | ✅ |

- `ADMIN` has global visibility and deletion rights.
- `MANAGER` can create/assign tasks and manage status for tasks they created or are assigned to.
- `USER` can only view and update the status of tasks assigned to them.

## JWT Authentication and Password Hashing
- Authentication is implemented via JWT bearer tokens.
- `auth/login` issues access and refresh tokens.
- `auth/refresh` issues new tokens from a valid refresh token.
- Passwords are hashed with `bcrypt` before storage.

## Infrastructure & Local Setup Guide
### Required environment variables (`.env.example` blueprint)
```env
DATABASE_URL=postgresql://admin_user:super_secret_password@db:5432/task_db
JWT_SECRET_KEY=replace_with_secure_key
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
POSTGRES_USER=admin_user
POSTGRES_PASSWORD=super_secret_password
POSTGRES_DB=task_db
```

### Docker Compose deployment
1. Build and start all services:
```bash
docker-compose up --build -d
```
2. Apply migrations (also executed automatically by `entrypoint.sh`):
```bash
docker-compose exec web alembic upgrade head
```
3. Confirm services are running:
```bash
docker-compose ps
```
4. Open API docs `http://localhost:8000/docs`

### Runtime notes
- API service listens on port `8000`.
- PostgreSQL listens on port `5432`.
- Redis listens on port `6379`.
- Celery worker runs as a separate container and consumes tasks from Redis.

## Cache & Background Task Workflows

- Redis caching is applied via `@cache_response(ttl_seconds=..., prefix=...)` on list endpoints.

- The decorator builds a unique cache key from request query parameters while excluding runtime-only dependencies like `db` and `current_user`.

- Cached responses accelerate repeated page and search hits for tasks and users.

- Celery is configured in `app/core/celery_app.py` and runs in the `celery_worker` container.

- The sign-up flow uses `send_welcome_email.delay()` to enqueue email processing off the main request path.

## Assumptions & Known Limitations
- Database access remains synchronous by design; there is no async DB engine or async SQLAlchemy session.

- PostgreSQL is connected through `psycopg2` and standard synchronous session management.

- Initial setup assumes role seed data exists or is inserted before user registration.

- The task workflow intentionally blocks transitions from `COMPLETED` back to `PENDING`, enforcing forward-only status progression.
