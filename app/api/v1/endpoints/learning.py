"""
Learning Recommendation Service — Gợi ý lộ trình học tập cá nhân hóa
"""
import logging
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.utils.llm_client import complete
from app.utils.usage_logger import log_api_usage
from app.db.database import get_db
from app.db.entity.usage_log import UsageLog
from app.db.entity.llm_usage_log import LLMUsageLog
from app.db.entity.learning_recommendation import LearningRecommendation
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# Request/Response Models
# ============================================================
class LearningRequest(BaseModel):
    user_id: str = Field(..., description="ID của người dùng")
    learning_history: Optional[str] = Field(
        None, description="Lịch sử học tập")
    interests: List[str] = Field(...,
                                 description="Sở thích / lĩnh vực quan tâm", min_length=1)
    skill_level: str = Field(
        "beginner", description="Trình độ: beginner, intermediate, advanced, expert")
    goal: Optional[str] = Field(None, description="Mục tiêu học tập cụ thể")
    time_available_hours: int = Field(
        5, description="Số giờ có thể học mỗi tuần", ge=1, le=40)


class CourseRecommendation(BaseModel):
    course_name: str
    description: str
    difficulty: str
    estimated_hours: int
    priority: int
    topics: List[str]
    prerequisites: List[str]
    learning_objectives: List[str]


class LearningRecommendationResponse(BaseModel):
    success: bool
    user_id: str
    skill_level: str
    recommended_path: List[CourseRecommendation]
    alternative_suggestions: List[str]
    estimated_total_hours: int
    tip: str
    correlation_id: Optional[str] = None


# ============================================================
# System Prompt
# ============================================================
SYSTEM_RECOMMENDATION = """Bạn là chuyên gia tư vấn lộ trình học AI và lập trình.
Nhiệm vụ: Đề xuất lộ trình học tập cá nhân hóa dựa trên thông tin người dùng.

Yêu cầu:
1. Lộ trình phải logic, từ cơ bản đến nâng cao
2. Mỗi khóa học có mô tả rõ ràng, thời gian dự kiến
3. Ưu tiên các nguồn tài liệu miễn phí, chất lượng
4. Phù hợp với trình độ và thời gian của học viên
5. Đưa ra lời khuyên thực tế, khả thi

Trả về định dạng JSON với cấu trúc:
{
    "recommended_path": [...],
    "alternative_suggestions": [...],
    "total_hours": 50,
    "tip": "..."
}
"""


# ============================================================
# Fallback Recommendations
# ============================================================
def get_fallback_recommendations(interests: List[str], skill_level: str) -> Dict[str, Any]:
    course_map = {
        "python": {
            "beginner": {
                "course_name": "Python Cơ Bản",
                "topics": ["Biến và kiểu dữ liệu", "Câu lệnh điều kiện", "Vòng lặp", "Hàm"],
                "description": "Làm quen với Python từ số 0"
            },
            "intermediate": {
                "course_name": "Python Nâng Cao",
                "topics": ["OOP", "Decorator", "Generator", "Context Manager"],
                "description": "Chuyên sâu về Python"
            }
        },
        "machine_learning": {
            "beginner": {
                "course_name": "Machine Learning Cơ Bản",
                "topics": ["Linear Regression", "Logistic Regression", "Train/Test Split"],
                "description": "Nhập môn Machine Learning"
            }
        }
    }

    recommended_path = []
    priority = 1

    for interest in interests[:3]:
        interest_lower = interest.lower()
        if interest_lower in course_map:
            config = course_map[interest_lower]
            level_config = config.get(
                skill_level, config.get("beginner", config))
            course = level_config.copy()
            course["difficulty"] = skill_level
            course["estimated_hours"] = 15 if skill_level == "beginner" else 25
            course["priority"] = priority
            course["prerequisites"] = [
                "Không yêu cầu"] if skill_level == "beginner" else ["Kiến thức cơ bản"]
            course["learning_objectives"] = [
                f"Nắm vững {topic}" for topic in course.get("topics", [])]
            recommended_path.append(CourseRecommendation(**course))
            priority += 1

    return {
        "recommended_path": recommended_path,
        "alternative_suggestions": [
            "Tham khảo YouTube: 'FreeCodeCamp' và '3Blue1Brown'",
            "Thực hành trên Kaggle và LeetCode",
            "Đọc sách: 'Automate the Boring Stuff with Python'"
        ],
        "total_hours": sum(c.estimated_hours for c in recommended_path),
        "tip": "Học 30 phút mỗi ngày sẽ hiệu quả hơn học 4 tiếng vào cuối tuần!"
    }


def build_recommendation_prompt(payload: LearningRequest) -> str:
    prompt = f"""Thông tin người dùng:
- Trình độ hiện tại: {payload.skill_level}
- Sở thích / lĩnh vực quan tâm: {', '.join(payload.interests)}
- Thời gian có thể học mỗi tuần: {payload.time_available_hours} giờ
"""
    if payload.learning_history:
        prompt += f"- Lịch sử học tập: {payload.learning_history}\n"
    if payload.goal:
        prompt += f"- Mục tiêu: {payload.goal}\n"
    prompt += "\nHãy đề xuất lộ trình học tập phù hợp."
    return prompt


# ============================================================
# Main Endpoint (có database)
# ============================================================
@router.post("/recommend", response_model=LearningRecommendationResponse)
async def recommend_learning(
    request: Request,
    payload: LearningRequest,
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
        f"[{correlation_id}] Learning recommendation for user {payload.user_id}, db_user_id={user_id}")

    try:
        user_prompt = build_recommendation_prompt(payload)

        try:
            result_text = await complete(
                system=SYSTEM_RECOMMENDATION,
                user=user_prompt,
                correlation_id=correlation_id,
                user_id=user_id or 0,
                service_name="learning_recommendation",
                max_tokens=1500
            )

            start = result_text.find('{')
            end = result_text.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = result_text[start:end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")

            recommended_path = []
            for course in data.get("recommended_path", []):
                recommended_path.append(CourseRecommendation(**course))

            response_data = LearningRecommendationResponse(
                success=True,
                user_id=payload.user_id,
                skill_level=payload.skill_level,
                recommended_path=recommended_path,
                alternative_suggestions=data.get(
                    "alternative_suggestions", []),
                estimated_total_hours=data.get("total_hours", 50),
                tip=data.get("tip", "Học đều đặn mỗi ngày!"),
                correlation_id=correlation_id
            )

            # ========== LƯU VÀO DATABASE ==========
            latency_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000)

            # 1. Lưu vào learning_recommendations
            learning_rec = LearningRecommendation(
                user_id=user_id,
                correlation_id=correlation_id,
                weak_criteria=[],  # Learning không có weak_criteria
                recommended_path=data.get("recommended_path", []),
                total_hours=data.get("total_hours", 50),
                tip=data.get("tip", "")
            )
            db.add(learning_rec)

            # 2. Lưu vào usage_logs
            usage_log = UsageLog(
                correlation_id=correlation_id,
                user_id=user_id,
                api_key_id=api_key_id,
                service_name="learning",
                request_data=payload.model_dump_json(),
                response_data=json.dumps(
                    {"total_hours": data.get("total_hours", 0)}),
                prompt_tokens=len(user_prompt.split()),
                completion_tokens=len(result_text.split()),
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
                service_name="learning_recommendation",
                model_used=settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.GEMINI_MODEL,
                prompt_tokens=len(user_prompt.split()),
                completion_tokens=len(result_text.split()),
                total_tokens=len(user_prompt.split()) +
                len(result_text.split()),
                estimated_cost=(len(user_prompt.split()) +
                                len(result_text.split())) * 0.000001,
                cost_per_1k_tokens=0.001,
                latency_ms=latency_ms,
                time_to_first_token_ms=100,
                status="success",
                request_preview=user_prompt[:200],
                response_preview=result_text[:200] if result_text else None
            )
            db.add(llm_log)

            await db.commit()
            logger.info(
                f"[{correlation_id}] Learning recommendation saved, user_id={user_id}")

        except Exception as llm_error:
            logger.warning(
                f"[{correlation_id}] LLM failed, using fallback: {llm_error}")
            fallback = get_fallback_recommendations(
                payload.interests, payload.skill_level)

            response_data = LearningRecommendationResponse(
                success=True,
                user_id=payload.user_id,
                skill_level=payload.skill_level,
                recommended_path=fallback["recommended_path"],
                alternative_suggestions=fallback["alternative_suggestions"],
                estimated_total_hours=fallback["total_hours"],
                tip=fallback["tip"],
                correlation_id=correlation_id
            )

            # Fallback cũng lưu vào database
            latency_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000)

            learning_rec = LearningRecommendation(
                user_id=user_id,
                correlation_id=correlation_id,
                weak_criteria=[],
                recommended_path=fallback["recommended_path"],
                total_hours=fallback["total_hours"],
                tip=fallback["tip"]
            )
            db.add(learning_rec)

            usage_log = UsageLog(
                correlation_id=correlation_id,
                user_id=user_id,
                api_key_id=api_key_id,
                service_name="learning",
                request_data=payload.model_dump_json(),
                response_data=json.dumps({"fallback": True}),
                prompt_tokens=len(user_prompt.split()),
                completion_tokens=0,
                latency_ms=latency_ms,
                status="fallback",
                ip_address=ip_address,
                user_agent=user_agent[:500]
            )
            db.add(usage_log)
            await db.commit()

        return response_data

    except Exception as e:
        logger.error(
            f"[{correlation_id}] Learning recommendation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "LEARNING_001",
                "message": f"Failed to generate recommendations: {str(e)}",
                "correlation_id": correlation_id
            }
        )


# ============================================================
# Lấy gợi ý nhanh theo sở thích
# ============================================================
@router.get("/suggestions")
async def get_quick_suggestions(interest: Optional[str] = None):
    suggestions = {
        "python": ["Python Cơ Bản", "Python Nâng Cao", "Python cho Data Science"],
        "machine_learning": ["ML Cơ Bản", "ML Nâng Cao", "ML với Scikit-learn"],
        "deep_learning": ["Neural Networks", "Computer Vision", "NLP với Deep Learning"],
        "data_science": ["Pandas/NumPy", "Data Visualization", "SQL cho Data Science"],
        "ai": ["Nhập môn AI", "AI Agents", "Generative AI"]
    }
    if interest:
        interest_lower = interest.lower()
        for key in suggestions:
            if key in interest_lower:
                return {"interest": interest, "suggested_courses": suggestions[key]}
        return {"interest": interest, "suggested_courses": suggestions["python"]}
    return {"all_suggestions": suggestions}


@router.get("/health")
async def health_check():
    return {"service": "learning_recommendation", "status": "healthy"}
