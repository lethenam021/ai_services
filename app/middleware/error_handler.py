from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import datetime
import traceback
import json

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')

        try:
            response = await call_next(request)
            return response

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            user_message = "Internal server error. Please try again later."
            error_code = "ERR_500"

            # ============================================================
            # 1. LỖI QUOTA & RATE LIMIT
            # ============================================================
            if any(keyword in error_msg.lower() for keyword in [
                "quota", "resource_exhausted", "rate limit", "too many requests",
                "exceeded", "limit", "429", "RESOURCE_EXHAUSTED"
            ]):
                status_code = status.HTTP_429_TOO_MANY_REQUESTS
                error_code = "ERR_429_QUOTA"
                user_message = "API quota exceeded. Please try again in a few minutes."

            # ============================================================
            # 2. LỖI AUTHENTICATION (API Key)
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "api key", "invalid", "unauthorized", "authentication",
                "credential", "permission denied", "forbidden", "401"
            ]):
                status_code = status.HTTP_401_UNAUTHORIZED
                error_code = "ERR_401_AUTH"
                user_message = "Invalid or missing API key. Please check configuration."

            # ============================================================
            # 3. LỖI TIMEOUT
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "timeout", "timed out", "deadline", "504"
            ]):
                status_code = status.HTTP_504_GATEWAY_TIMEOUT
                error_code = "ERR_504_TIMEOUT"
                user_message = "Request timeout. Please try again."

            # ============================================================
            # 4. LỖI CONNECTION & NETWORK
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "connection", "network", "refused", "unreachable",
                "dns", "host", "socket", "reset", "broken pipe"
            ]):
                status_code = status.HTTP_502_BAD_GATEWAY
                error_code = "ERR_502_CONNECTION"
                user_message = "Cannot connect to AI service. Please check network."

            # ============================================================
            # 5. LỖI JSON PARSE
            # ============================================================
            elif isinstance(e, json.JSONDecodeError) or "json" in error_msg.lower():
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
                error_code = "ERR_422_JSON"
                user_message = "Invalid JSON response from AI service."

            # ============================================================
            # 6. LỖI VALIDATION (Pydantic)
            # ============================================================
            elif "validation" in error_msg.lower() or "pydantic" in error_type.lower():
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
                error_code = "ERR_422_VALIDATION"
                user_message = "Invalid request data format."

            # ============================================================
            # 7. LỖI DATABASE
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "database", "sql", "connection refused", "postgres",
                "mysql", "sqlite", "alembic", "asyncpg"
            ]):
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                error_code = "ERR_503_DATABASE"
                user_message = "Database service unavailable. Please try again later."

            # ============================================================
            # 8. LỖI REDIS / CACHE
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "redis", "cache", "connection refused"
            ]):
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                error_code = "ERR_503_CACHE"
                user_message = "Cache service unavailable. Please try again later."

            # ============================================================
            # 9. LỖI PRESIDIO (Privacy Detector)
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "presidio", "spacy", "nlp", "model not found"
            ]):
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                error_code = "ERR_503_PRIVACY"
                user_message = "Privacy detection service unavailable."

            # ============================================================
            # 10. LỖI FILE NOT FOUND
            # ============================================================
            elif "no such file" in error_msg.lower() or "not found" in error_msg.lower():
                status_code = status.HTTP_404_NOT_FOUND
                error_code = "ERR_404_NOT_FOUND"
                user_message = "Requested resource not found."

            # ============================================================
            # 11. LỖI BAD REQUEST
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "bad request", "invalid input", "missing field"
            ]):
                status_code = status.HTTP_400_BAD_REQUEST
                error_code = "ERR_400_BAD_REQUEST"
                user_message = "Invalid request. Please check your input."

            # ============================================================
            # 12. LỖI RATE LIMIT (Custom)
            # ============================================================
            elif "rate limit" in error_msg.lower():
                status_code = status.HTTP_429_TOO_MANY_REQUESTS
                error_code = "ERR_429_RATE_LIMIT"
                user_message = "Too many requests. Please slow down."

            # ============================================================
            # 13. LỖI MEMORY / RESOURCE
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "memory", "out of memory", "resource", "too large"
            ]):
                status_code = status.HTTP_507_INSUFFICIENT_STORAGE
                error_code = "ERR_507_MEMORY"
                user_message = "Request too large or system out of memory."

            # ============================================================
            # 14. LỖI DEPENDENCY / IMPORT
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "no module", "import", "dependency", "package not found"
            ]):
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                error_code = "ERR_500_DEPENDENCY"
                user_message = "Service dependency missing. Please contact administrator."

            # ============================================================
            # 15. LỖI MODEL (AI/ML)
            # ============================================================
            elif any(keyword in error_msg.lower() for keyword in [
                "model", "inference", "predict", "transformers"
            ]):
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                error_code = "ERR_503_MODEL"
                user_message = "AI model service unavailable."

            # ============================================================
            # 16. LỖI UNKNOWN (Fallback)
            # ============================================================
            else:
                # Log chi tiết lỗi không xác định
                logger.error(
                    f"[{correlation_id}] Unhandled error type: {error_type}\n"
                    f"Message: {error_msg}\n"
                    f"Traceback: {traceback.format_exc()}"
                )

            # Log lỗi
            logger.error(
                f"[{correlation_id}] Error {status_code} [{error_code}]: "
                f"{error_type} - {error_msg[:200]}"
            )

            # Trả về JSON response
            return JSONResponse(
                status_code=status_code,
                content={
                    "success": False,
                    "error_code": error_code,
                    "status_code": status_code,
                    "message": user_message,
                    "detail": error_msg[:500] if status_code >= 500 else None,
                    "correlation_id": correlation_id,
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                }
            )
