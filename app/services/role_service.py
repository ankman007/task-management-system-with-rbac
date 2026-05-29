from sqlalchemy.orm import Session
from typing import List
from app.models import Role
from app.models import RoleName, User
from fastapi import HTTPException, status


class RoleService:
    @staticmethod
    def get_all_roles(db: Session, current_user: User) -> List[Role]:
        if current_user.role.name != RoleName.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied. Only Administrators can view system roles.",
            )
        return db.query(Role).order_by(Role.id).all()
