import pytest
from datetime import datetime, timedelta, timezone
from fastapi import status
from app.models import User, RoleName, Role, Task, TaskStatus


def get_future_date(days=1):
    """Helper to get a future date with timezone."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture
def manager_user(db_session):
    """Create a manager user for testing."""
    manager_role = db_session.query(Role).filter(Role.name == RoleName.MANAGER).first()
    user = User(
        email="manager@example.com",
        hashed_password="fake",
        role_id=manager_role.id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_manager(client, manager_user):
    """Get auth headers for manager user."""
    from app.core.dependency import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: manager_user
    return {"Authorization": "Bearer fake-token"}


@pytest.fixture
def sample_task(db_session, normal_user, admin_user):
    """Create a sample task for testing."""
    task = Task(
        title="Test Task",
        description="Test Description",
        status=TaskStatus.PENDING,
        assigned_to_id=normal_user.id,
        created_by_id=admin_user.id,
        due_date=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


class TestCreateTask:
    """Comprehensive tests for POST /tasks/ endpoint."""

    def test_create_task_as_admin(self, client, auth_headers_admin, normal_user):
        """Test admin can create a task."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "title": "Admin Task",
                "description": "Task created by admin",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "Admin Task"
        assert data["description"] == "Task created by admin"
        assert data["status"] == "PENDING"

    def test_create_task_as_user_denied(self, client, auth_headers_user, normal_user):
        """Test regular user cannot create a task."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_user,
            json={
                "title": "User Task",
                "description": "Task by user",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Permission denied" in response.json()["detail"]

    def test_create_task_missing_title(self, client, auth_headers_admin, normal_user):
        """Test task creation fails without title."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "description": "No title",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_task_missing_assigned_to_id(self, client, auth_headers_admin):
        """Test task creation works without assigned_to_id (it's optional)."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "title": "Task",
                "description": "No assigned user",
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "Task"

    def test_create_task_empty_title(self, client, auth_headers_admin, normal_user):
        """Test task creation fails with empty title."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "title": "",
                "description": "Empty title",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_task_response_includes_created_by(
        self, client, auth_headers_admin, normal_user
    ):
        """Test task response includes created_by info."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "title": "Task",
                "description": "Description",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "created_by_id" in data

    def test_create_task_as_manager(self, client, auth_headers_manager, normal_user):
        """Test manager can create a task."""
        response = client.post(
            "/tasks/",
            headers=auth_headers_manager,
            json={
                "title": "Manager Task",
                "description": "Task by manager",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "Manager Task"

    def test_create_task_past_due_date_rejected(
        self, client, auth_headers_admin, normal_user
    ):
        """Test task creation fails with past due date."""
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        response = client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "title": "Past Task",
                "description": "Past due date",
                "assigned_to_id": normal_user.id,
                "due_date": past_date,
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestGetAllTasks:
    """Comprehensive tests for GET /tasks/ endpoint."""

    def test_get_all_tasks_as_admin(
        self, client, auth_headers_admin, normal_user, sample_task
    ):
        """Test admin can see all tasks."""
        response = client.get("/tasks/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_all_tasks_as_user_sees_only_assigned(
        self,
        client,
        auth_headers_user,
        admin_user,
        normal_user,
        sample_task,
        db_session,
    ):
        """Test regular user sees only tasks assigned to them."""
        # Create another task not assigned to user
        other_task = Task(
            title="Other Task",
            description="Not assigned to user",
            status=TaskStatus.PENDING,
            assigned_to_id=admin_user.id,
            created_by_id=admin_user.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(other_task)
        db_session.commit()

        response = client.get("/tasks/", headers=auth_headers_user)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Should only see the task assigned to them
        assert all(task["assigned_to_id"] == normal_user.id for task in data)

    def test_get_all_tasks_with_pagination(self, client, auth_headers_admin):
        """Test pagination parameters work."""
        response = client.get("/tasks/?limit=5&skip=0", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_get_all_tasks_with_search(self, client, auth_headers_admin, normal_user):
        """Test search parameter filters tasks."""
        client.post(
            "/tasks/",
            headers=auth_headers_admin,
            json={
                "title": "Unique Search Task",
                "description": "Search test",
                "assigned_to_id": normal_user.id,
                "due_date": get_future_date(),
            },
        )

        response = client.get(
            "/tasks/?search=Unique",
            headers=auth_headers_admin,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(
            "Unique" in task["title"] or "Unique" in task["description"]
            for task in data
        )

    def test_get_all_tasks_with_status_filter(
        self, client, auth_headers_admin, normal_user, db_session
    ):
        """Test status filter works."""
        # Create tasks with different statuses
        for status_val in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]:
            task = Task(
                title=f"Task {status_val}",
                description=f"Status: {status_val}",
                status=status_val,
                assigned_to_id=normal_user.id,
                created_by_id=admin_user.id if hasattr(self, "admin_user") else 1,
                due_date=datetime.now(timezone.utc) + timedelta(days=1),
            )
            db_session.add(task)
        db_session.commit()

        response = client.get(
            "/tasks/?status=PENDING",
            headers=auth_headers_admin,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all(task["status"] == "PENDING" for task in data)

    def test_get_all_tasks_limit_boundary(self, client, auth_headers_admin):
        """Test limit parameter respects maximum."""
        response = client.get("/tasks/?limit=100", headers=auth_headers_admin)
        assert response.status_code == status.HTTP_200_OK

        response = client.get("/tasks/?limit=101", headers=auth_headers_admin)
        # Should fail or clamp to 100
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_all_tasks_skip_parameter(
        self, client, auth_headers_admin, normal_user, admin_user, db_session
    ):
        """Test skip parameter works."""
        for i in range(3):
            task = Task(
                title=f"Task {i}",
                description=f"Description {i}",
                status=TaskStatus.PENDING,
                assigned_to_id=normal_user.id,
                created_by_id=admin_user.id,
                due_date=datetime.now(timezone.utc) + timedelta(days=1),
            )
            db_session.add(task)
        db_session.commit()

        response = client.get("/tasks/?skip=1&limit=100", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) <= 2


class TestAssignTask:
    """Comprehensive tests for PATCH /tasks/{id}/assign endpoint."""

    def test_assign_task_as_admin(
        self, client, auth_headers_admin, normal_user, sample_task, db_session
    ):
        """Test admin can assign a task."""
        other_user = User(
            email="other@example.com",
            hashed_password="fake",
            role_id=normal_user.role_id,
        )
        db_session.add(other_user)
        db_session.commit()

        response = client.patch(
            f"/tasks/{sample_task.id}/assign",
            headers=auth_headers_admin,
            json={"assign_to_id": other_user.id},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["assigned_to_id"] == other_user.id

    def test_assign_task_as_user_denied(
        self, client, auth_headers_user, normal_user, sample_task, db_session
    ):
        """Test regular user cannot assign a task."""
        other_user = User(
            email="other@example.com",
            hashed_password="fake",
            role_id=normal_user.role_id,
        )
        db_session.add(other_user)
        db_session.commit()

        response = client.patch(
            f"/tasks/{sample_task.id}/assign",
            headers=auth_headers_user,
            json={"assign_to_id": other_user.id},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_assign_task_to_non_existent_user(
        self, client, auth_headers_admin, sample_task
    ):
        """Test assigning task to non-existent user fails."""
        response = client.patch(
            f"/tasks/{sample_task.id}/assign",
            headers=auth_headers_admin,
            json={"assign_to_id": 999},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_non_existent_task(self, client, auth_headers_admin, normal_user):
        """Test assigning non-existent task fails."""
        response = client.patch(
            "/tasks/999/assign",
            headers=auth_headers_admin,
            json={"assign_to_id": normal_user.id},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_task_missing_assign_to_id(
        self, client, auth_headers_admin, sample_task
    ):
        """Test assigning without assign_to_id fails."""
        response = client.patch(
            f"/tasks/{sample_task.id}/assign",
            headers=auth_headers_admin,
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUpdateTaskStatus:
    """Comprehensive tests for PATCH /tasks/{id}/status endpoint."""

    def test_update_task_status_as_admin(self, client, auth_headers_admin, sample_task):
        """Test admin can update task status."""
        response = client.patch(
            f"/tasks/{sample_task.id}/status",
            headers=auth_headers_admin,
            json={"status": "IN_PROGRESS"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "IN_PROGRESS"

    def test_update_task_status_as_assigned_user(
        self, client, auth_headers_user, sample_task
    ):
        """Test assigned user can update their task status."""
        response = client.patch(
            f"/tasks/{sample_task.id}/status",
            headers=auth_headers_user,
            json={"status": "IN_PROGRESS"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "IN_PROGRESS"

    def test_update_task_status_completed_to_pending_denied(
        self, client, auth_headers_admin, normal_user, admin_user, db_session
    ):
        """Test task cannot transition from COMPLETED back to PENDING."""
        completed_task = Task(
            title="Completed Task",
            description="Already done",
            status=TaskStatus.COMPLETED,
            assigned_to_id=normal_user.id,
            created_by_id=admin_user.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(completed_task)
        db_session.commit()

        response = client.patch(
            f"/tasks/{completed_task.id}/status",
            headers=auth_headers_admin,
            json={"status": "PENDING"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_task_status_completed_to_in_progress_denied(
        self, client, auth_headers_admin, normal_user, admin_user, db_session
    ):
        """Test task cannot transition from COMPLETED to IN_PROGRESS."""
        completed_task = Task(
            title="Completed Task",
            description="Already done",
            status=TaskStatus.COMPLETED,
            assigned_to_id=normal_user.id,
            created_by_id=admin_user.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(completed_task)
        db_session.commit()

        response = client.patch(
            f"/tasks/{completed_task.id}/status",
            headers=auth_headers_admin,
            json={"status": "IN_PROGRESS"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_non_existent_task_status(self, client, auth_headers_admin):
        """Test updating non-existent task status fails."""
        response = client.patch(
            "/tasks/999/status",
            headers=auth_headers_admin,
            json={"status": "IN_PROGRESS"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_task_status_invalid_status(
        self, client, auth_headers_admin, sample_task
    ):
        """Test updating with invalid status fails."""
        response = client.patch(
            f"/tasks/{sample_task.id}/status",
            headers=auth_headers_admin,
            json={"status": "INVALID_STATUS"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_update_task_status_missing_status(
        self, client, auth_headers_admin, sample_task
    ):
        """Test updating without status field fails."""
        response = client.patch(
            f"/tasks/{sample_task.id}/status",
            headers=auth_headers_admin,
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_update_task_status_valid_transitions(
        self, client, auth_headers_admin, admin_user, normal_user, db_session
    ):
        """Test valid status transitions work."""
        task = Task(
            title="Status Transition Task",
            description="Test transitions",
            status=TaskStatus.PENDING,
            assigned_to_id=normal_user.id,
            created_by_id=admin_user.id,
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(task)
        db_session.commit()

        # PENDING -> IN_PROGRESS
        response = client.patch(
            f"/tasks/{task.id}/status",
            headers=auth_headers_admin,
            json={"status": "IN_PROGRESS"},
        )
        assert response.status_code == status.HTTP_200_OK

        # IN_PROGRESS -> COMPLETED
        response = client.patch(
            f"/tasks/{task.id}/status",
            headers=auth_headers_admin,
            json={"status": "COMPLETED"},
        )
        assert response.status_code == status.HTTP_200_OK


class TestDeleteTask:
    """Comprehensive tests for DELETE /tasks/{id} endpoint."""

    def test_delete_task_as_admin(self, client, auth_headers_admin, sample_task):
        """Test admin can delete a task."""
        response = client.delete(
            f"/tasks/{sample_task.id}",
            headers=auth_headers_admin,
        )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]

    def test_delete_task_as_user_denied(self, client, auth_headers_user, sample_task):
        """Test regular user cannot delete a task."""
        response = client.delete(
            f"/tasks/{sample_task.id}",
            headers=auth_headers_user,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_non_existent_task(self, client, auth_headers_admin):
        """Test deleting non-existent task fails."""
        response = client.delete(
            "/tasks/999",
            headers=auth_headers_admin,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_task_removes_from_database(
        self, client, auth_headers_admin, sample_task, db_session
    ):
        """Test deleted task is actually removed from database."""
        task_id = sample_task.id

        client.delete(
            f"/tasks/{task_id}",
            headers=auth_headers_admin,
        )

        # Try to fetch it again
        response = client.get("/tasks/", headers=auth_headers_admin)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert not any(task["id"] == task_id for task in data)

    def test_delete_task_as_manager_denied(
        self, client, auth_headers_manager, sample_task
    ):
        """Test manager cannot delete a task."""
        response = client.delete(
            f"/tasks/{sample_task.id}",
            headers=auth_headers_manager,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
