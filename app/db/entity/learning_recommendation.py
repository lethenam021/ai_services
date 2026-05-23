from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.base import Base


class LearningRecommendation(Base):
    __tablename__ = "learning_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    weak_criteria: Mapped[list] = mapped_column(JSON)
    recommended_path: Mapped[dict] = mapped_column(JSON)
    total_hours: Mapped[int] = mapped_column(Integer)
    tip: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
