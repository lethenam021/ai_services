"""
Ghi nhận mọi lần gọi LLM vào database
Dùng cho: Admin dashboard thống kê, theo dõi chi phí, phát hiện abuse
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Pricing reference (USD per 1K tokens) — cập nhật khi đổi model
PRICING = {
    "gpt-4o-mini":    {"input": 0.00015, "output": 0.00060},
    "gpt-4o":         {"input": 0.00500, "output": 0.01500},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.00030},
}


def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = PRICING.get(model, {"input": 0.001, "output": 0.002})
    return (
        prompt_tokens / 1000 * pricing["input"]
        + completion_tokens / 1000 * pricing["output"]
    )


async def log_api_usage(
    correlation_id: str,
    user_id: int,
    service_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str,
):
    """
    Insert vào bảng api_usage_logs
    Trong production: dùng SQLAlchemy async session
    """
    cost = _calc_cost(model, prompt_tokens, completion_tokens)

    logger.info(
        "API_USAGE | cid=%s | user=%s | service=%s | model=%s | "
        "tokens=%d+%d | cost=$%.6f | latency=%dms | status=%s",
        correlation_id, user_id, service_name, model,
        prompt_tokens, completion_tokens, cost, latency_ms, status,
    )

    # TODO: Insert vào DB
    # async with get_db_session() as session:
    #     log = ApiUsageLog(
    #         correlation_id=correlation_id,
    #         user_id=user_id,
    #         service_name=service_name,
    #         model_used=model,
    #         prompt_tokens=prompt_tokens,
    #         completion_tokens=completion_tokens,
    #         total_cost_usd=cost,
    #         latency_ms=latency_ms,
    #         status=status,
    #         created_at=datetime.utcnow(),
    #     )
    #     session.add(log)
    #     await session.commit()
