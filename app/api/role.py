from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.dependency import get_current_user
from app.models import User
from app.schemas.role import RoleResponse
from app.services.role_service import RoleService

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("/", response_model=List[RoleResponse])
def view_all_roles(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return RoleService.get_all_roles(db=db, current_user=current_user)
