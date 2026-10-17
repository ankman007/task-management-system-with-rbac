from typing import TYPE_CHECKING

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RoleName

if TYPE_CHECKING:
    from app.models.user import User


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[RoleName] = mapped_column(
        Enum(RoleName, name="role_name"), unique=True
    )

    users: Mapped[list["User"]] = relationship(back_populates="role", lazy="raise")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
