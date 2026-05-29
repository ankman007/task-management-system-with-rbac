from sqlalchemy.orm import Session
from typing import List, Optional
from app.models import RoleName, User
from fastapi import HTTPException, status


class UserService:
    @staticmethod
    def view_all_users(
        db: Session,
        current_user: User,
        limit: int,
        skip: int,
        search: Optional[str] = None,
    ) -> List[User]:

        if current_user.role.name != RoleName.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied. Only Administrators can view user information.",
            )

        query = db.query(User)

        if search:
            query = query.filter(User.email.ilike(f"%{search}%"))

        return query.order_by(User.id).offset(skip).limit(limit).all()
