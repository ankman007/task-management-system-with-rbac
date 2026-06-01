# Task Management System API with RBAC

Built with FastAPI and PostgreSQL, featuring strict Role-Based Access Control (RBAC), Redis caching and Celery background workers.

<!-- Tech Stack Badges -->
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-373737?style=for-the-badge&logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features & Implemented Requirements](#key-features--implemented-requirements)
- [Infrastructure & Local Setup Guide](#infrastructure--local-setup-guide)
  - [Required Environment Variables](#required-environment-variables)
  - [Docker Compose Deployment](#docker-compose-deployment)
  - [Runtime Notes](#runtime-notes)
- [System Architecture & Design](#system-architecture--design)
  - [System Architecture](#system-architecture)
  - [Database Design](#database-design)
- [Security & RBAC Implementation Matrix](#security--rbac-implementation-matrix)
- [Technical Deep Dive](#technical-deep-dive)
  - [Architecture & Approach](#architecture--approach)
  - [JWT Authentication and Password Hashing](#jwt-authentication-and-password-hashing)
  - [Cache & Background Task Workflows](#cache--background-task-workflows)
- [Project Structure & Test Suite](#project-structure--test-suite)
  - [Project Structure](#project-structure)
  - [Test Suite & Validation Coverage](#test-suite--validation-coverage)
- [Assumptions & Known Limitations](#assumptions--known-limitations)

---

## Project Overview

The Task Management System API is a high-performance backend enterprise solution designed to securely manage task workflows. Built on a foundation of strict Role-Based Access Control (RBAC), the system ensures isolation of user data and granular permission enforcement across different organizational roles. 

To maintain high API responsiveness and unblock the client request lifecycle, the architecture utilizes a dual-layer optimization strategy: offloading intensive background processing to an asynchronous worker pool and implementing low-latency caching for read-heavy operations.

[Postman Collection Documentation](https://documenter.getpostman.com/view/32993281/2sBXwntrnU#77d965fe-1678-44f8-ba80-33b71e04e17a)

---

## Key Features & Implemented Requirements
  - JWT authentication with access + refresh tokens.
  - Granular RBAC for `ADMIN`, `MANAGER`, and `USER`.
  - Task workflow enforcing strict transitions: `PENDING -> IN_PROGRESS -> COMPLETED` and blocking completed-to-pending rollback.
  - Automated testing suite built with Pytest that validates routes, schemas, security gates, and database transactions in an isolated environment.
  - Docker Compose orchestration for API, PostgreSQL, Redis, and Celery worker.
  - Pagination and multi-parameter filtering/search for users and tasks.
  - Interactive custom Swagger docs at `/docs` route.
  - Redis caching decorators for repeated search and page hits.
  - Asynchronous Celery email worker pipeline for background notification simulation.

---

## Infrastructure & Local Setup Guide
### Required environment variables
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

---

## System Architecture & Design

### System Architecture
<img width="1536" height="886" alt="System_Architecture_Diagram_Task_Management_System" src="https://github.com/user-attachments/assets/5e960796-4f71-4f7f-8da5-d9175a16f2ea" />

The system is built around a FastAPI application that handles authentication, authorization, and task management logic. PostgreSQL serves as the primary datastore for users, roles, and tasks, while Redis is used for response caching and as the message broker for Celery. Background jobs, such as welcome email processing, are delegated to Celery workers to keep API requests fast and responsive.

### Database Design
<img width="1368" height="371" alt="ER_Diagram_Task Management System" src="https://github.com/user-attachments/assets/5eecea40-c968-4f84-95fe-cea0d6f6cb1c" />

The data model consists of three core entities: Roles, Users, and Tasks. Each user is assigned a single role that determines their permissions, while tasks are linked to both a creator and an optional assignee. This structure enables strict role-based access control and clear ownership and assignment relationships throughout the task lifecycle.

## Security & RBAC Implementation Matrix
| Role | View all users | View/Create tasks | Assign tasks | Update task status | Delete tasks | Status workflow enforcement |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `ADMIN` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `MANAGER` | ❌ | ✅ | ✅ | ✅ (own or assigned tasks only) | ❌ | ✅ |
| `USER` | ❌ | ❌ | ❌ | ✅ (assigned tasks only) | ❌ | ✅ |

- `ADMIN` has global visibility and deletion rights.
- `MANAGER` can create/assign tasks and manage status for tasks they created or are assigned to.
- `USER` can only view and update the status of tasks assigned to them.

---

## Technical Deep Dive

### Architecture & Approach
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
 
### JWT Authentication and Password Hashing
- Authentication is implemented via JWT bearer tokens.
- `auth/login` issues access and refresh tokens.
- `auth/refresh` issues new tokens from a valid refresh token.
- Passwords are hashed with `bcrypt` before storage.

### Cache & Background Task Workflows

- Redis caching is applied via `@cache_response(ttl_seconds=..., prefix=...)` on list endpoints.
- The decorator builds a unique cache key from request query parameters while excluding runtime-only dependencies like `db` and `current_user`.
- Cached responses accelerate repeated page and search hits for tasks and users.
- Celery is configured in `app/core/celery_app.py` and runs in the `celery_worker` container.
- The sign-up flow uses `send_welcome_email.delay()` to enqueue email processing off the main request path.

---

## Project Structure & Test Suite

### Project Structure
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

### Test Suite & Validation Coverage
The repository includes a comprehensive Pytest suite that automatically validates routes, schemas, security gates, and database transactions in an isolated environment.

```text
tests/
  ├── conftest.py      # Session-specific mocks, token generation helpers, and user seeds
  ├── test_auth.py     # JWT generation, registration endpoints, and login verification
  ├── test_roles.py    # System role validation and RBAC edge-case testing
  ├── test_users.py    # User profile management and administrative path security
  └── test_tasks.py    # Workflow status transitions and task restriction gates
```

To run the test suite locally run run following docker command: 
```bash
docker-compose exec web pytest -v --disable-warnings
```

These tests ensure the API is secure, orderly, and private by locking down user access and data boundaries. They verify that only logged-in users with the right permissions can modify their own tasks, while strictly enforcing that tasks only move forward through their lifecycle phases.

---

## Assumptions & Known Limitations
- Database access remains synchronous by design; there is no async DB engine or async SQLAlchemy session.

- PostgreSQL is connected through `psycopg2` and standard synchronous session management.

- Initial setup assumes role seed data exists or is inserted before user registration.

- The task workflow intentionally blocks transitions from `COMPLETED` back to `PENDING`, enforcing forward-only status progression.
