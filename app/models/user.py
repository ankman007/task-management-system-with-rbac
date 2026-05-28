from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)

    role = relationship("Role", back_populates="users")
    
    created_tasks = relationship("Task", foreign_keys="Task.created_by_id", back_populates="creator")
    assigned_tasks = relationship("Task", foreign_keys="Task.assigned_to_id", back_populates="assignee")