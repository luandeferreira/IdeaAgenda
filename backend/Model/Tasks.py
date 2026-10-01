from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base
import uuid

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    summary = Column(String, index=True)
    description = Column(String, index=True)
    location = Column(String, index=True)
    completion_date = Column(DateTime, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, default=None)
    completed = Column(Boolean, default=False)

    calendar_id = Column(UUID(as_uuid=True), ForeignKey("calendar.id"))
    calendar = relationship("Calendar", back_populates="tasks")
