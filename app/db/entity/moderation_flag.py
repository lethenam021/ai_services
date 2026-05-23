from sqlalchemy import String, Integer, DateTime, JSON, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.base import Base


class ModerationFlag(Base):
    __tablename__ = "moderation_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(
        "users.id"), nullable=True)  # ← THÊM DÒNG NÀY
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(String(2000))
    categories: Mapped[list] = mapped_column(JSON)
    risk_score: Mapped[float] = mapped_column(Float)
    action_taken: Mapped[str] = mapped_column(String(50))  # allow, warn, block
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
