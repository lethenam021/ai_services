from sqlalchemy import String, Integer, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.base import Base


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False)

    # User tracking
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_keys.id"), nullable=True)

    # Service info
    service_name: Mapped[str] = mapped_column(
        String(50), nullable=False)  # quiz, suggestion, expert
    # groq/llama-3.1-8b-instant, gemini-2.0-flash
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)

    # Token usage
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking (USD)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_1k_tokens: Mapped[float] = mapped_column(Float, default=0.0)

    # Performance
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    time_to_first_token_ms: Mapped[int] = mapped_column(
        Integer, nullable=True)  # For streaming

    # Status
    # success, error, timeout, rate_limit
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # Request/Response (optional, for debugging)
    request_preview: Mapped[str] = mapped_column(String(500), nullable=True)
    response_preview: Mapped[str] = mapped_column(String(500), nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
