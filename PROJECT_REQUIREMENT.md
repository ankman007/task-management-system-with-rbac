# Technical Task: Task Management API with RBAC

**Tech Stack:** Python, FastAPI, PostgreSQL, SQLAlchemy, JWT  
*(Bonus: Alembic, Async, Docker, Pytest, Redis)* 

**Estimated Time:** 5–8 hours

---

## 1. Database Schema & Models

Implement a relational database structure with the following entities:

* **`users`**: `id`, `email`, `hashed_password`, `role_id`
* **`roles`**: `id`, `name` (`ADMIN`, `MANAGER`, `USER`)
* **`tasks`**: `id`, `title`, `description`, `status` (`PENDING`, `IN_PROGRESS`, `COMPLETED`), `due_date`, `assigned_to` (FK -> `users`), `created_by` (FK -> `users`)

---

## 2. RBAC & Module Requirements

### Authentication Module
* `POST /auth/register` (New users default to `USER` role; passwords must be hashed)
* `POST /auth/login` (Returns JWT token)

### Task Module & Permissions Matrix

| Action | API Endpoint | ADMIN | MANAGER | USER |
| :--- | :--- | :---: | :---: | :---: |
| **Create Task** | `POST /tasks` | ✅ | ✅ | ❌ |
| **View All Tasks** | `GET /tasks` | ✅ (All) | ✅ (Created/Assigned) | ✅ (Only Assigned) |
| **Assign Task** | `PATCH /tasks/{id}/assign` | ✅ | ✅ | ❌ |
| **Update Status** | `PATCH /tasks/{id}/status` | ✅ | ✅ | ✅ (Only Assigned) |
| **Delete Task** | `DELETE /tasks/{id}` | ✅ | ❌ | ❌ |

> ⚠️ **Status Workflow Rule:** Statuses must be validated. A task marked `COMPLETED` cannot transition back to `PENDING`.

---

## 3. Code Architecture Expectations

Maintain a strict, modular separation of concerns. Do not pack business logic into route files.

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

## 4. Technical Guardrails

* **Validation:** Strict Pydantic request validation and structured global error handling.
* **HTTP Statuses:** Return explicit, semantic codes (e.g., `201 Created`, `401 Unauthorized`, `403 Forbidden`).
* **Security:** Use reusable dependencies (`Depends`) for authentication and role-based route protection.

---

## 5. Submission Deliverables

1. **GitHub Repository:** Clean commit history, structured codebase.
2. **README:** Setup guide, `.env.example`, architecture notes, and local run instructions.
3. **Database State:** Alembic migration files or an ERD diagram.
4. **API Testing:** Postman/Bruno collection or a customized Swagger UI setup.

---

## 🎯 Evaluation Weights

* **Functional Logic (RBAC & Auth):** 35%
* **Architecture & Code Quality:** 35%
* **Database Design:** 15%
* **Validation & Error Handling:** 10%
* **Documentation & Git:** 5%
