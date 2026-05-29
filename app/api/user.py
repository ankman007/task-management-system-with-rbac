from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.core.dependency import get_current_user
from app.models import User
from app.schemas.user import UserResponse
from app.services.user_service import UserService
from app.core.decorators import cache_response

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=List[UserResponse])
@cache_response(ttl_seconds=300, prefix="users")
def view_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(
        default=10, le=100, description="Maximum number of records to return"
    ),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    search: Optional[str] = Query(default=None, description="Search users by email"),
):
    return UserService.view_all_users(
        db=db, current_user=current_user, limit=limit, skip=skip, search=search
    )
