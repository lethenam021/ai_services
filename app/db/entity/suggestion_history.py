from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.base import Base


class SuggestionHistory(Base):
    __tablename__ = "suggestion_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    anonymized_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    weak_criteria: Mapped[list] = mapped_column(JSON)
    domain: Mapped[str] = mapped_column(String(50))
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
