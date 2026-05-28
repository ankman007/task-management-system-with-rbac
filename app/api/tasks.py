from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.dependency import get_current_user
from app.models.user import User
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate, TaskResponse
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.post("/", response_model=TaskResponse)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return TaskService.create_task(db=db, task_in=task_in, current_user=current_user)


@router.get("/", response_model=List[TaskResponse])
def view_all_tasks(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return TaskService.get_tasks(db=db, current_user=current_user)


@router.patch("/{id}/assign", response_model=TaskResponse)
def assign_task(id: int, assign_to_id: int = Body(embed=True), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return TaskService.assign_task(db=db, task_id=id, assign_to_id=assign_to_id, current_user=current_user)


@router.patch("/{id}/status", response_model=TaskResponse)
def update_task_status(id: int, status: TaskStatus = Body(embed=True), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return TaskService.update_status(db=db, task_id=id, new_status=status, current_user=current_user)


@router.delete("/{id}")
def delete_task(id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return TaskService.delete_task(db=db, task_id=id, current_user=current_user)