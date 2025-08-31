# app/models/question.py
from sqlalchemy import Column, String, JSON, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID
from app.services.db import Base
import uuid

class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stem = Column(String, nullable=False)
    options = Column(JSON, nullable=False)
    answer = Column(String, nullable=False)
    source_doc_id = Column(String, nullable=True)

    # NEW FIELDS
    explanation = Column(Text, nullable=True)      # model’s reasoning/rationale
    difficulty = Column(String(16), nullable=True) # "easy" | "medium" | "hard"
    topic = Column(String(128), nullable=True)     # short tag/topic

    created_at = Column(DateTime(timezone=True), server_default=func.now())
