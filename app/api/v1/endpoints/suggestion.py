"""S3 — Prompt Suggestion Endpoint (Streaming SSE)"""
import logging
import json
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schemas import SuggestionRequest
from app.utils.llm_client import stream_suggestion
from app.db.database import get_db
from app.db.entity.usage_log import UsageLog
from app.db.entity.llm_usage_log import LLMUsageLog
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate")
async def generate_suggestion(
    request: Request,
    body: SuggestionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sinh gợi ý cải thiện prompt bằng LLM — trả về dạng Stream SSE.
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

    logger.info(
        f"[{correlation_id}] Suggestion request for domain: {body.domain}, user_id={user_id}")

    # Biến để đếm token
    token_count = 0
    full_response = []

    async def token_generator():
        nonlocal token_count, full_response
        try:
            async for token in stream_suggestion(
                anonymized_prompt=body.anonymized_prompt,
                weak_criteria=body.score_result.weak_criteria,
                domain=body.domain,
                correlation_id=correlation_id,
                user_id=user_id or 0,
            ):
                token_count += len(token)
                full_response.append(token)
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"

            # Sau khi stream xong, lưu vào database
            latency_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000)
            response_text = "".join(full_response)

            # 1. Lưu vào usage_logs
            usage_log = UsageLog(
                correlation_id=correlation_id,
                user_id=user_id,
                api_key_id=api_key_id,
                service_name="suggestion",
                request_data=body.model_dump_json(),
                response_data=json.dumps({"suggestion": response_text[:500]}),
                prompt_tokens=len(body.anonymized_prompt.split()),
                completion_tokens=token_count,
                latency_ms=latency_ms,
                status="success",
                ip_address=ip_address,
                user_agent=user_agent[:500]
            )
            db.add(usage_log)

          
            # 2. Lưu vào llm_usage_logs
            llm_log = LLMUsageLog(
                correlation_id=correlation_id,
                user_id=user_id,
                api_key_id=api_key_id,
                service_name="suggestion",
                model_used="groq/llama-3.1-8b-instant",  # hoặc "gemini-2.0-flash"
                prompt_tokens=len(body.anonymized_prompt.split()),
                completion_tokens=token_count,
                total_tokens=len(body.anonymized_prompt.split()) + token_count,
                estimated_cost=(len(body.anonymized_prompt.split()) + token_count) * 0.000001,  # ~$0.001/1M tokens
                cost_per_1k_tokens=0.001,
                latency_ms=latency_ms,
                time_to_first_token_ms=100,  # optional, cho streaming
                status="success",
                request_preview=body.anonymized_prompt[:200],
                response_preview=response_text[:200] if response_text else None
            )
            db.add(llm_log)




            await db.commit()
            logger.info(
                f"[{correlation_id}] Suggestion saved, tokens={token_count}, user_id={user_id}")

        except Exception as e:
            logger.error(f"[{correlation_id}] Suggestion stream error: {e}")
            # Lưu log lỗi
            error_log = UsageLog(
                correlation_id=correlation_id,
                user_id=user_id,
                api_key_id=api_key_id,
                service_name="suggestion",
                request_data=body.model_dump_json(),
                response_data=None,
                prompt_tokens=len(body.anonymized_prompt.split()),
                completion_tokens=0,
                latency_ms=int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000),
                status="error",
                error_message=str(e)[:500],
                ip_address=ip_address,
                user_agent=user_agent[:500]
            )
            db.add(error_log)
            await db.commit()
            yield f"data: [Lỗi: {str(e)}]\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )
