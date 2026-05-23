"""
Expert Assistance Service — Trợ giảng AI chuyên sâu
"""
import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.utils.llm_client import complete
from app.utils.usage_logger import log_api_usage
from app.db.database import get_db
from app.db.entity.usage_log import UsageLog
from app.db.entity.llm_usage_log import LLMUsageLog
from app.db.entity.expert_conversation import ExpertConversation
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# Request/Response Models
# ============================================================
class ExpertRequest(BaseModel):
    question: str = Field(..., description="Câu hỏi của học viên",
                          min_length=5, max_length=2000)
    expertise_area: str = Field(
        "general", description="Lĩnh vực chuyên môn: general, programming, math, science, language")
    context: Optional[str] = Field(None, description="Ngữ cảnh bổ sung")
    max_tokens: int = Field(
        500, description="Độ dài tối đa câu trả lời", ge=100, le=2000)


class ExpertResponse(BaseModel):
    success: bool
    answer: str
    expertise_area: str
    sources: Optional[List[str]] = None
    related_questions: Optional[List[str]] = None
    correlation_id: Optional[str] = None


# ============================================================
# System Prompts theo từng lĩnh vực
# ============================================================
SYSTEM_PROMPTS = {
    "general": """Bạn là trợ giảng AI thân thiện. Nhiệm vụ:
- Trả lời câu hỏi một cách dễ hiểu, chính xác
- Sử dụng ví dụ cụ thể để minh họa
- Ngôn ngữ tiếng Việt, gần gũi với học viên
- Nếu không biết, hãy nói "Tôi chưa có thông tin về điều này"
- Không bịa ra thông tin sai lệch""",

    "programming": """Bạn là chuyên gia lập trình. Nhiệm vụ:
- Giải thích khái niệm code với ví dụ thực tế
- Đưa ra code mẫu ngắn gọn, dễ hiểu
- Giải thích best practices và common pitfalls
- Hỗ trợ các ngôn ngữ: Python, JavaScript, Java, C++
- Trả lời bằng tiếng Việt, thuật ngữ chuyên ngành giữ nguyên""",

    "math": """Bạn là gia sư Toán. Nhiệm vụ:
- Giải thích từng bước, không bỏ qua bước nào
- Dùng công thức rõ ràng, định dạng đẹp
- Đưa ra bài tập tương tự để luyện tập
- Phân tích lỗi sai thường gặp
- Ngôn ngữ tiếng Việt, dễ hiểu cho học sinh""",

    "science": """Bạn là chuyên gia Khoa học. Nhiệm vụ:
- Giải thích hiện tượng khoa học bằng ngôn ngữ đơn giản
- Liên hệ với thực tế và ứng dụng
- Đưa ra thí nghiệm đơn giản có thể tự làm
- Phân biệt giả thuyết và sự thật khoa học
- Trả lời bằng tiếng Việt, chính xác và trực quan""",

    "language": """Bạn là giáo viên Ngôn ngữ. Nhiệm vụ:
- Giải thích ngữ pháp, từ vựng dễ hiểu
- Đưa ra ví dụ câu cụ thể
- Giải thích thành ngữ, cách diễn đạt tự nhiên
- Sửa lỗi câu từ nếu có
- Trả lời bằng tiếng Việt hoặc tiếng Anh tùy câu hỏi"""
}


async def generate_related_questions(question: str, expertise_area: str, answer: str) -> List[str]:
    suggestions = {
        "programming": [
            "Làm thế nào để debug code hiệu quả?",
            "Sự khác nhau giữa function và method?",
            "Best practices cho clean code là gì?"
        ],
        "math": [
            "Có mẹo nào để nhớ công thức không?",
            "Làm sao để tránh sai sót khi tính toán?",
            "Ứng dụng thực tế của kiến thức này?"
        ],
        "general": [
            "Có tài liệu nào để học thêm không?",
            "Làm sao để nhớ kiến thức lâu hơn?",
            "Bài tập thực hành ở đâu?"
        ]
    }
    return suggestions.get(expertise_area, suggestions["general"])


# ============================================================
# Main Endpoint (có database)
# ============================================================
@router.post("/ask", response_model=ExpertResponse)
async def expert_assist(
    request: Request,
    payload: ExpertRequest,
    db: AsyncSession = Depends(get_db)
):
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
        f"[{correlation_id}] Expert assist request: area={payload.expertise_area}, user_id={user_id}")

    try:
        system_prompt = SYSTEM_PROMPTS.get(
            payload.expertise_area, SYSTEM_PROMPTS["general"])

        user_prompt = f"Câu hỏi: {payload.question}\n"
        if payload.context:
            user_prompt += f"Ngữ cảnh: {payload.context}\n"
        user_prompt += "\nHãy trả lời chi tiết, dễ hiểu."

        answer = await complete(
            system=system_prompt,
            user=user_prompt,
            correlation_id=correlation_id,
            user_id=user_id or 0,
            service_name="expert_assist",
            max_tokens=payload.max_tokens
        )

        related_questions = await generate_related_questions(payload.question, payload.expertise_area, answer)

        # ========== LƯU VÀO DATABASE ==========
        latency_ms = int(
            (datetime.utcnow() - start_time).total_seconds() * 1000)

        # 1. Lưu vào expert_conversations
        conversation = ExpertConversation(
            user_id=user_id,
            correlation_id=correlation_id,
            question=payload.question,
            answer=answer,
            expertise_area=payload.expertise_area,
            max_tokens=payload.max_tokens,
            latency_ms=latency_ms
        )
        db.add(conversation)

        # 2. Lưu vào usage_logs
        usage_log = UsageLog(
            correlation_id=correlation_id,
            user_id=user_id,
            api_key_id=api_key_id,
            service_name="expert",
            request_data=payload.model_dump_json(),
            response_data=json.dumps({"answer": answer[:500]}),
            prompt_tokens=len(payload.question.split()),
            completion_tokens=len(answer.split()),
            latency_ms=latency_ms,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent[:500]
        )
        db.add(usage_log)

        # 3. Lưu vào llm_usage_logs
        llm_log = LLMUsageLog(
            correlation_id=correlation_id,
            user_id=user_id,
            api_key_id=api_key_id,
            service_name="expert_assist",
            model_used=settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.GEMINI_MODEL,
            prompt_tokens=len(payload.question.split()),
            completion_tokens=len(answer.split()),
            total_tokens=len(payload.question.split()) + len(answer.split()),
            estimated_cost=(len(payload.question.split()) +
                            len(answer.split())) * 0.000001,
            cost_per_1k_tokens=0.001,
            latency_ms=latency_ms,
            time_to_first_token_ms=100,
            status="success",
            request_preview=payload.question[:200],
            response_preview=answer[:200]
        )
        db.add(llm_log)

        await db.commit()

        logger.info(
            f"[{correlation_id}] Expert conversation saved, user_id={user_id}, tokens={len(answer.split())}")

        return ExpertResponse(
            success=True,
            answer=answer,
            expertise_area=payload.expertise_area,
            sources=None,
            related_questions=related_questions,
            correlation_id=correlation_id
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{correlation_id}] Expert assist error: {error_msg}")

        # Lưu log lỗi
        error_log = UsageLog(
            correlation_id=correlation_id,
            user_id=user_id,
            api_key_id=api_key_id,
            service_name="expert",
            request_data=payload.model_dump_json(),
            response_data=None,
            prompt_tokens=len(payload.question.split()),
            completion_tokens=0,
            latency_ms=int(
                (datetime.utcnow() - start_time).total_seconds() * 1000),
            status="error",
            error_message=error_msg[:500],
            ip_address=ip_address,
            user_agent=user_agent[:500]
        )
        db.add(error_log)
        await db.commit()

        if "quota" in error_msg.lower() or "RESOURCE_EXHAUSTED" in error_msg:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "EXPERT_001",
                    "message": "API quota exceeded. Please try again in a few minutes.",
                    "correlation_id": correlation_id
                }
            )

        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "EXPERT_002",
                "message": f"Failed to get expert response: {str(e)}",
                "correlation_id": correlation_id
            }
        )


# ============================================================
# Lấy danh sách lĩnh vực
# ============================================================
@router.get("/areas")
async def get_available_areas():
    return {
        "areas": list(SYSTEM_PROMPTS.keys()),
        "descriptions": {
            "general": "Câu hỏi chung, kiến thức phổ thông",
            "programming": "Lập trình, code, thuật toán",
            "math": "Toán học, công thức, bài tập",
            "science": "Khoa học, vật lý, hóa học, sinh học",
            "language": "Ngôn ngữ, ngữ pháp, từ vựng"
        }
    }


@router.get("/health")
async def health_check():
    return {"service": "expert_assist", "status": "healthy"}
