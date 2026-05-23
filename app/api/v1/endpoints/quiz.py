"""S4 — Quiz Generation Endpoint"""
import json
import logging
import hashlib
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schemas import QuizGenRequest, QuizGenResponse
from app.utils.llm_client import complete
from app.db.database import get_db
from app.db.entity.quiz import Quiz
from app.db.entity.usage_log import UsageLog
from app.db.entity.llm_usage_log import LLMUsageLog
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)

SYSTEM_QUIZ = """Bạn là chuyên gia giáo dục về AI. Tạo câu hỏi quiz từ nội dung bài học.
Trả về JSON hợp lệ với format:
{
  "questions": [{"question":"...","options":["A","B","C","D"],"correct_answer":"A","explanation":"..."}],
  "lesson_summary": "..."
}
Chỉ trả về JSON, không có text khác."""


def truncate_json_str(data: str, max_length: int = 10000) -> str:
    """Truncate JSON string nếu quá dài"""
    if len(data) <= max_length:
        return data
    logger.warning(f"JSON data truncated: {len(data)} -> {max_length}")
    return data[:max_length]


@router.post("/generate", response_model=QuizGenResponse)
async def generate_quiz(
    request: Request,
    body: QuizGenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Tự động sinh câu hỏi quiz từ nội dung bài học.
    Dùng bởi Chuyên gia / Admin khi tạo bài học mới.
    """
    cid = getattr(request.state, 'correlation_id', 'unknown')
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

    # Dùng nội dung đã ẩn danh nếu có
    lesson_content = body.lesson_content
    if body.privacy_result and body.privacy_result.anonymized_prompt:
        lesson_content = body.privacy_result.anonymized_prompt
        logger.info(f"[{cid}] Using anonymized content")

    user_msg = f"""Nội dung bài học:
{lesson_content}

Yêu cầu: {body.num_questions} câu, độ khó {body.difficulty}"""

    try:
        result_text = await complete(
            SYSTEM_QUIZ,
            user_msg,
            cid,
            user_id or 0,
            "quiz_generation",
            max_tokens=2000
        )
    except Exception as e:
        logger.error(f"[{cid}] Quiz generation LLM error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "QUIZ_001",
                "message": f"LLM error: {str(e)}",
                "correlation_id": cid
            }
        )

    # Clean response (remove markdown wrapper if any)
    result_text = result_text.strip()
    if result_text.startswith("```json"):
        result_text = result_text[7:]
    if result_text.startswith("```"):
        result_text = result_text[3:]
    if result_text.endswith("```"):
        result_text = result_text[:-3]

    try:
        data = json.loads(result_text)
    except json.JSONDecodeError as e:
        logger.error(f"[{cid}] JSON parse error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "QUIZ_002",
                "message": "Invalid JSON response from LLM",
                "correlation_id": cid
            }
        )

    # ========== LƯU VÀO DATABASE ==========
    latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    content_hash = hashlib.md5(lesson_content.encode()).hexdigest()

    # 1. Lưu vào bảng quizzes
    quiz_record = Quiz(
        user_id=user_id,
        correlation_id=cid,
        lesson_content_hash=content_hash,
        num_questions=body.num_questions,
        difficulty=body.difficulty,
        questions=data.get("questions", []),
        lesson_summary=data.get("lesson_summary", "")
    )
    db.add(quiz_record)

    # 2. Lưu vào usage_logs
    usage_log = UsageLog(
        correlation_id=cid,
        user_id=user_id,
        api_key_id=api_key_id,
        service_name="quiz",
        request_data=truncate_json_str(body.model_dump_json()),
        response_data=truncate_json_str(json.dumps(data)),
        prompt_tokens=len(lesson_content.split()),
        completion_tokens=len(data.get("questions", [])) * 20,
        latency_ms=latency_ms,
        status="success",
        ip_address=ip_address,
        user_agent=user_agent[:500]
    )
    db.add(usage_log)

    # 3. Lưu vào llm_usage_logs (track token cho LLM)
    # 2. Lưu vào llm_usage_logs
    llm_log = LLMUsageLog(
        correlation_id=cid,
        user_id=user_id,
        api_key_id=api_key_id,
        service_name="quiz",
        model_used="groq/llama-3.1-8b-instant",
        prompt_tokens=len(lesson_content.split()),
        completion_tokens=len(data.get("questions", [])) * 20,
        total_tokens=len(lesson_content.split()) +
        len(data.get("questions", [])) * 20,
        estimated_cost=(len(lesson_content.split()) +
                        len(data.get("questions", [])) * 20) * 0.000001,
        cost_per_1k_tokens=0.001,
        latency_ms=latency_ms,
        time_to_first_token_ms=100,
        status="success",
        request_preview=lesson_content[:200],
        response_preview=json.dumps(data)[:200] if data else None
    )
    db.add(llm_log)

    await db.commit()

    logger.info(
        f"[{cid}] Quiz saved: {body.num_questions} questions, user_id={user_id}")

    return QuizGenResponse(**data)
