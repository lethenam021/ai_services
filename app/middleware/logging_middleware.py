from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import AsyncSessionLocal
from app.db.entity.usage_log import UsageLog
import time
import json


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')

        # Đọc body (cần lưu lại để log)
        body = await request.body()

        response = await call_next(request)

        # Log sau khi response
        latency_ms = int((time.time() - start_time) * 1000)

        # Lưu log bất đồng bộ (không chặn response)
        async with AsyncSessionLocal() as db:
            log = UsageLog(
                correlation_id=correlation_id,
                service_name=request.url.path.split(
                    "/")[-2] if "/api/v1/" in request.url.path else "unknown",
                request_data=body[:1000].decode('utf-8', errors='ignore'),
                latency_ms=latency_ms,
                status="success" if response.status_code < 400 else "error"
            )
            db.add(log)
            await db.commit()

        return response
