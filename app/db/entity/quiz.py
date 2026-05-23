from sqlalchemy import Float, String, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.base import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    lesson_content_hash: Mapped[str] = mapped_column(String(64))
    num_questions: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(20))
    questions: Mapped[dict] = mapped_column(JSON)  # list of questions
    lesson_summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    answers: Mapped[dict] = mapped_column(JSON)
    score: Mapped[float] = mapped_column(Float)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
