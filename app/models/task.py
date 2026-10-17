from datetime import date, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TaskStatus

if TYPE_CHECKING:
    from app.models.user import User


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # Visibility queries filter by owner/assignee and sort by recency.
        Index("ix_tasks_assigned_to_created_at", "assigned_to", "created_at"),
        Index("ix_tasks_created_by_created_at", "created_by", "created_at"),
        # ADMINs list every task, newest first.
        Index("ix_tasks_created_at_id", "created_at", "id"),
    )
    # Fetch server-generated values (created_at, updated_at) with RETURNING on
    # INSERT/UPDATE, so no extra refresh is needed in async code.
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
        index=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # lazy="raise" turns an accidental async lazy-load into a clear error.
    assignee: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_to], lazy="raise"
    )
    creator: Mapped["User"] = relationship(foreign_keys=[created_by], lazy="raise")

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.status}>"
