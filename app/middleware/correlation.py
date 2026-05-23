"""
Gắn Correlation ID vào mọi request để trace xuyên suốt .NET → FastAPI → LLM
"""
import logging
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Đọc từ .NET nếu có, tự sinh nếu không
        correlation_id = request.headers.get("X-Correlation-Id", str(uuid4()))

        # Gắn vào request state để các service đọc
        request.state.correlation_id = correlation_id

        logger.info(
            f"[{correlation_id}] --> {request.method} {request.url.path}"
        )

        response = await call_next(request)

        # Trả về trong response header để .NET log lại
        response.headers["X-Correlation-Id"] = correlation_id

        logger.info(
            f"[{correlation_id}] <-- {response.status_code}"
        )

        return response
