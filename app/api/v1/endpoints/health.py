"""Health check endpoint — dùng cho Docker healthcheck và .NET monitoring"""
import logging
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.privacy.detector import PrivacyDetector
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

START_TIME = datetime.utcnow()


class HealthResponse(BaseModel):
    status: str          # "healthy" | "degraded" | "unhealthy"
    version: str
    uptime_seconds: float
    checks: dict[str, bool]
    timestamp: datetime


async def check_llm_connectivity() -> bool:
    """Check LLM connectivity based on configured provider"""

    # Nếu đang dùng Gemini
    if settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
            response = await model.generate_content_async("Hi")
            return True
        except Exception as e:
            logger.warning(f"Gemini connectivity check failed: {e}")
            return False

    # Fallback cho OpenAI
    elif settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-fake"):
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            await client.models.list()
            return True
        except Exception:
            return False

    return False


@router.get("", response_model=HealthResponse)
async def health_check():
    checks = {
        "privacy_detector": PrivacyDetector._initialized,
        "scoring_service":  True,   # Rule-based, luôn healthy
        "llm_connectivity": await check_llm_connectivity(),
    }

    all_ok = all(checks.values())
    critical_ok = checks["privacy_detector"] and checks["scoring_service"]

    if all_ok:
        status = "healthy"
    elif critical_ok:
        status = "degraded"   # LLM down nhưng core services vẫn chạy
    else:
        status = "unhealthy"

    uptime = (datetime.utcnow() - START_TIME).total_seconds()

    logger.info("Health check: status=%s", status)

    return HealthResponse(
        status=status,
        version="1.0.0",
        uptime_seconds=uptime,
        checks=checks,
        timestamp=datetime.utcnow(),
    )
