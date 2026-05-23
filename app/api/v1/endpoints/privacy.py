"""S1 — Privacy Filter Endpoint"""
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schemas import PrivacyScanRequest, PrivacyScanResponse
from app.services.privacy.detector import PrivacyDetector
from app.db.database import get_db
from app.db.entity.usage_log import UsageLog
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/scan", response_model=PrivacyScanResponse)
async def scan_privacy(
    request: Request,
    body: PrivacyScanRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Quét prompt để phát hiện dữ liệu cá nhân nhạy cảm.
    Trả về prompt đã ẩn danh và danh sách cảnh báo.
    Luôn gọi endpoint này ĐẦU TIÊN trước mọi service khác.
    """
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    start_time = datetime.utcnow()
    
    # Lấy user_id từ API key
    api_key_header = request.headers.get("X-Internal-Key")
    user_id = None
    api_key_id = None
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")
    
    if api_key_header:
        result = await db.execute(
            select(APIKey).where(
                APIKey.key == api_key_header,
                APIKey.is_active == True
            )
        )
        api_key_obj = result.scalar_one_or_none()
        if api_key_obj:
            user_id = api_key_obj.user_id
            api_key_id = api_key_obj.id
            api_key_obj.last_used_at = datetime.utcnow()
            await db.commit()
    
    logger.info(f"[{correlation_id}] Privacy scan request, user_id={user_id}, prompt length={len(body.prompt)}")
    
    # Gọi privacy detector
    result = await PrivacyDetector.scan(body, correlation_id)
    
    # ========== LƯU VÀO DATABASE ==========
    latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    usage_log = UsageLog(
        correlation_id=correlation_id,
        user_id=user_id,
        api_key_id=api_key_id,
        service_name="privacy",
        request_data=body.model_dump_json(),
        response_data=result.model_dump_json(),
        prompt_tokens=len(body.prompt.split()),
        completion_tokens=len(result.anonymized_prompt.split()) if result.anonymized_prompt else 0,
        latency_ms=latency_ms,
        status="success",
        ip_address=ip_address,
        user_agent=user_agent[:500]
    )
    db.add(usage_log)
    await db.commit()
    
    logger.info(f"[{correlation_id}] Privacy scan completed, has_sensitive={result.has_sensitive}, risk_level={result.risk_level}")
    
    return result