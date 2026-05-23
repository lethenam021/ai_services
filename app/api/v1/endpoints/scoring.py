"""S2 — Prompt Scoring Endpoint"""
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json

from app.models.schemas import ScoringRequest, ScoringResponse
from app.services.scoring.scorer import PromptScorer
from app.db.database import get_db
from app.db.entity.usage_log import UsageLog
from app.db.entity.scoring_history import ScoringHistory
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)


def truncate_json_str(data: str, max_length: int = 10000) -> str:
    """Truncate JSON string nếu quá dài"""
    if len(data) <= max_length:
        return data
    logger.warning(f"JSON data truncated: {len(data)} -> {max_length}")
    return data[:max_length]


@router.post("/evaluate", response_model=ScoringResponse)
async def evaluate_prompt(
    request: Request,
    body: ScoringRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Chấm điểm prompt theo 8 tiêu chí (rule-based, không tốn token).
    Nhận kết quả Privacy từ S1 để tính điểm tiêu chí Safety.
    """
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    logger.info(f"[{correlation_id}] ========== START SCORING ==========")
    logger.info(f"[{correlation_id}] Domain: {body.domain}")
    logger.info(f"[{correlation_id}] Prompt length: {len(body.prompt)}")

    # ========== 1. Lấy user_id từ API key ==========
    api_key_header = request.headers.get("X-Internal-Key")
    logger.info(
        f"[{correlation_id}] API Key: {api_key_header[:30] if api_key_header else 'None'}...")

    user_id = None
    api_key_id = None
    ip_address = request.client.host if request.client else None
    user_agent_str = request.headers.get("user-agent", "")

    if api_key_header:
        try:
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
                logger.info(
                    f"[{correlation_id}] ✅ Found user_id: {user_id}, api_key_id: {api_key_id}")

                api_key_obj.last_used_at = datetime.utcnow()
                await db.commit()
                logger.info(
                    f"[{correlation_id}] Updated last_used_at for API key")
            else:
                logger.warning(
                    f"[{correlation_id}] ⚠️ API key not found in database or inactive")
        except Exception as e:
            logger.error(f"[{correlation_id}] Error querying API key: {e}")

    # ========== 2. Gọi scoring service ==========
    try:
        result = await PromptScorer.evaluate(body, correlation_id, user_id)
        logger.info(
            f"[{correlation_id}] Scoring result: total_score={result.total_score}, grade={result.grade}, passed={result.passed}")
    except Exception as e:
        logger.error(f"[{correlation_id}] Scoring service error: {e}")
        raise HTTPException(status_code=500, detail=f"Scoring error: {str(e)}")

    # ========== 3. Lưu vào scoring_history ==========
    try:
        history = ScoringHistory(
            user_id=user_id,
            correlation_id=correlation_id,
            prompt_text=body.prompt[:1000],
            domain=body.domain,
            total_score=result.total_score,
            grade=result.grade,
            criteria_scores={k: v.model_dump()
                             for k, v in result.criteria.items()},
            weak_criteria=result.weak_criteria,
            passed=result.passed
        )
        db.add(history)
        logger.info(f"[{correlation_id}] ✅ Added to scoring_history")
        await db.flush()  # Force insert để catch lỗi sớm
    except Exception as e:
        logger.error(
            f"[{correlation_id}] Error adding to scoring_history: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"History error: {str(e)}")

    # ========== 4. Lưu vào usage_logs ==========
    try:
        usage_log = UsageLog(
            correlation_id=correlation_id,
            user_id=user_id,
            api_key_id=api_key_id,
            service_name="scoring",
            request_data=truncate_json_str(body.model_dump_json()),
            response_data=truncate_json_str(result.model_dump_json()),
            prompt_tokens=len(body.prompt.split()),
            completion_tokens=0,
            latency_ms=0,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent_str[:500]
        )
        db.add(usage_log)
        logger.info(f"[{correlation_id}] ✅ Added to usage_logs")
    except Exception as e:
        logger.error(f"[{correlation_id}] Error adding to usage_logs: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Usage log error: {str(e)}")

    # ========== 5. Commit transaction ==========
    try:
        await db.commit()
        logger.info(f"[{correlation_id}] ✅ Database commit successful")
    except Exception as e:
        logger.error(f"[{correlation_id}] Commit error: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Database error: {str(e)}")

    logger.info(f"[{correlation_id}] ========== END SCORING ==========")
    return result
