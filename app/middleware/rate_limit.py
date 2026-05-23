import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

# Simple in-memory rate limit (không cần Redis)
rate_limit_store = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Lấy API key hoặc IP
        api_key = request.headers.get("X-Internal-Key", "unknown")
        key = f"rate_limit:{api_key}"

        # 10 requests per 60 seconds
        limit = 10
        window = 60

        now = time.time()

        # Khởi tạo hoặc cleanup cũ
        if key not in rate_limit_store:
            rate_limit_store[key] = []

        # Xóa requests cũ hơn window
        rate_limit_store[key] = [
            t for t in rate_limit_store[key] if now - t < window]

        # Kiểm tra limit
        if len(rate_limit_store[key]) >= limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMIT_001",
                    "message": "Rate limit exceeded",
                    "retry_after": window,
                    "limit": limit,
                    "window_seconds": window
                }
            )

        # Thêm request hiện tại
        rate_limit_store[key].append(now)

        return await call_next(request)
