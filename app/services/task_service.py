from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models import RoleName, Task, User
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate


class TaskService:
    @staticmethod
    def create_task(db: Session, task_in: TaskCreate, current_user: User) -> Task:

        # Check to ensure only ADMIN or MANAGER can create tasks.
        if current_user.role.name == RoleName.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied. Users cannot create tasks.",
            )

        # Validate assigned user exists only if assigned_to_id is provided
        if task_in.assigned_to_id is not None:
            assigned_user = (
                db.query(User).filter(User.id == task_in.assigned_to_id).first()
            )

            if not assigned_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assigned user not found",
                )

        db_task = Task(
            title=task_in.title,
            description=task_in.description,
            due_date=task_in.due_date,
            assigned_to_id=task_in.assigned_to_id,
            created_by_id=current_user.id,
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return db_task

    @staticmethod
    def get_tasks(
        db: Session,
        current_user: User,
        limit: int,
        skip: int,
        search: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[Task]:

        query = db.query(Task)

        # Check to ensure a MANAGER can see a task only if they created it OR if it is assigned to them
        if current_user.role.name == RoleName.MANAGER:
            query = query.filter(
                or_(
                    Task.created_by_id == current_user.id,
                    Task.assigned_to_id == current_user.id,
                )
            )

        # Check to ensure a USER can only see tasks explicitly assigned to them
        elif current_user.role.name == RoleName.USER:
            query = query.filter(Task.assigned_to_id == current_user.id)

        # 3. Apply optional status filter
        if status:
            query = query.filter(Task.status == status)

        # 4. Apply optional search Bonus filter for title and description
        if search:
            query = query.filter(
                or_(
                    Task.title.ilike(f"%{search}%"),
                    Task.description.ilike(f"%{search}%"),
                )
            )

        return query.order_by(Task.due_date.asc()).offset(skip).limit(limit).all()

    @staticmethod
    def assign_task(
        db: Session, task_id: int, assign_to_id: int, current_user: User
    ) -> Task:

        # Check to ensure only ADMIN or MANAGER can assign tasks.
        if current_user.role.name == RoleName.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied. Users cannot assign tasks.",
            )

        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )
        assigned_user = db.query(User).filter(User.id == assign_to_id).first()

        if not assigned_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assigned user not found",
            )

        task.assigned_to_id = assign_to_id
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def update_status(
        db: Session, task_id: int, new_status: TaskStatus, current_user: User
    ) -> Task:

        task = db.query(Task).filter(Task.id == task_id).first()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        # Check to ensure that only assigned users or admins & managers can update the status
        if current_user.role.name == RoleName.USER:
            if task.assigned_to_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied. You are not assigned to this task.",
                )
        elif current_user.role.name == RoleName.MANAGER:
            if (
                task.created_by_id != current_user.id
                and task.assigned_to_id != current_user.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied. Managers can only update status for tasks they created or are assigned to.",
                )

        # Check to ensure that tasks cannot transition from COMPLETED back to PENDING
        if task.status == TaskStatus.COMPLETED and new_status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow validation error: Completed tasks cannot transition back to Pending status.",
            )

        task.status = new_status
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def delete_task(db: Session, task_id: int, current_user: User) -> dict:

        # Check to ensure that only ADMIN can delete tasks
        if current_user.role.name != RoleName.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied. Only Administrators can delete tasks.",
            )

        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        db.delete(task)
        db.commit()
        return {"detail": "Task successfully deleted"}
