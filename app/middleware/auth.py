from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from datetime import datetime
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.entity.api_key import APIKey
import logging

logger = logging.getLogger(__name__)


class InternalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Cho phép Swagger UI và health check
        if request.url.path in ["/docs",
                                "/openapi.json",
                                "/redoc",
                                "/health",
                                "/admin",           # ← Thêm dòng này
                                "/admin/users",     # ← Thêm
                                "/admin/api-keys",  # ← Thêm
                                "/admin/logs",      # ← Thêm
                                "/admin/stats",     # ← Thêm
                                "/admin/api/pages/dashboard",  # ← Thêm
                                "/admin/api/pages/users",      # ← Thêm
                                "/admin/api/pages/api-keys",   # ← Thêm
                                "/admin/api/pages/logs",       # ← Thêm
                                "/admin/api/pages/stats",      # ← Thêm
                                ]:
            return await call_next(request)

        # Lấy API key từ header
        api_key = request.headers.get("X-Internal-Key")

        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "AUTH_001",
                    "message": "Missing X-Internal-Key header",
                    "user_message": "Vui lòng cung cấp API key"
                }
            )

        logger.debug(
            f"Auth check: api_key={api_key[:20]}..., master_key={settings.INTERNAL_API_KEY[:20]}...")

        # 1. Kiểm tra master key (từ .env) trước
        if api_key == settings.INTERNAL_API_KEY:
            logger.info(f"✅ Master key authenticated")
            return await call_next(request)

        logger.info(f"Master key not matched, checking database...")
        # 2. Kiểm tra user key trong database
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(APIKey).where(
                    APIKey.key == api_key,
                    APIKey.is_active == True
                )
            )
            db_key = result.scalar_one_or_none()

            if not db_key:
                logger.warning(
                    f"❌ API key not found in database: {api_key[:30]}...")
                return JSONResponse(
                    status_code=401,
                    content={
                        "error_code": "AUTH_001",
                        "message": "Invalid X-Internal-Key",
                        "user_message": "API key không hợp lệ hoặc đã hết hạn"
                    }
                )

            # Cập nhật thời gian sử dụng cuối
            db_key.last_used_at = datetime.utcnow()
            await db.commit()
            logger.info(f"✅ DB key authenticated: user_id={db_key.user_id}")

        return await call_next(request)
