from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import List

from app.models import Task, User, RoleName
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate, TaskUpdate

class TaskService:

    @staticmethod
    def create_task(db: Session, task_in: TaskCreate, current_user: User) -> Task:
        # Matrix Check: ADMIN and MANAGER can create tasks. USER cannot.
        if current_user.role.name == RoleName.USER:
            raise HTTPException(status_code=403, detail="Permission denied. Users cannot create tasks.")
            
        db_task = Task(
            title=task_in.title,
            description=task_in.description,
            due_date=task_in.due_date,
            assigned_to_id=task_in.assigned_to_id,
            created_by_id=current_user.id
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return db_task

    @staticmethod
    def get_tasks(db: Session, current_user: User) -> List[Task]:
        # Matrix Check:
        # ADMIN sees all tasks
        if current_user.role.name == RoleName.ADMIN:
            return db.query(Task).all()
        # MANAGER sees tasks they created OR tasks assigned to them
        elif current_user.role.name == RoleName.MANAGER:
            return db.query(Task).filter(
                (Task.created_by_id == current_user.id) | (Task.assigned_to_id == current_user.id)
            ).all()
        # USER sees only tasks assigned to them
        else:
            return db.query(Task).filter(Task.assigned_to_id == current_user.id).all()

    @staticmethod
    def assign_task(db: Session, task_id: int, assign_to_id: int, current_user: User) -> Task:
        # Matrix Check: ADMIN and MANAGER can assign tasks. USER cannot.
        if current_user.role.name == RoleName.USER:
            raise HTTPException(status_code=403, detail="Permission denied. Users cannot assign tasks.")
            
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        task.assigned_to_id = assign_to_id
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def update_status(db: Session, task_id: int, new_status: TaskStatus, current_user: User) -> Task:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # Matrix Check: ADMIN & MANAGER can update any task. USER can only update if assigned.
        if current_user.role.name == RoleName.USER and task.assigned_to_id != current_user.id:
            raise HTTPException(status_code=403, detail="Permission denied. You are not assigned to this task.")
            
        # ⚠️ Status Workflow Rule: A task marked COMPLETED cannot transition back to PENDING.
        if task.status == TaskStatus.COMPLETED and new_status == TaskStatus.PENDING:
            raise HTTPException(
                status_code=400, 
                detail="Workflow validation error: Completed tasks cannot transition back to Pending status."
            )
            
        task.status = new_status
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def delete_task(db: Session, task_id: int, current_user: User) -> dict:
        # Matrix Check: Only ADMIN can delete tasks.
        if current_user.role.name != RoleName.ADMIN:
            raise HTTPException(status_code=403, detail="Permission denied. Only Administrators can delete tasks.")
            
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
            
        db.delete(task)
        db.commit()
        return {"detail": "Task successfully deleted"}