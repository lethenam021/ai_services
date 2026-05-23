"""
Shared Pydantic models — Input/Output schemas cho tất cả AI Services
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════
#  SHARED
# ══════════════════════════════════════════════════════════════

ALLOWED_DOMAINS = {"marketing", "programming",
                   "writing", "office", "data", "education"}

FORBIDDEN_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "jailbreak",
    "dan mode",
    "act as",
    "forget your instructions",
]


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    user_message: str       # Tiếng Việt, hiển thị trực tiếp cho user
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════════════════
#  S1 — PRIVACY FILTER
# ══════════════════════════════════════════════════════════════

class PrivacyScanRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)

    @field_validator("prompt")
    @classmethod
    def no_injection(cls, v: str) -> str:
        lower = v.lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in lower:
                raise ValueError(
                    f"Prompt contains forbidden pattern: '{pattern}'")
        return v


class PrivacyEntity(BaseModel):
    entity_type: str    # EMAIL, PHONE, CCCD, ADDRESS, API_KEY, PASSWORD, CREDIT_CARD
    value: str
    start: int
    end: int
    risk_level: str     # LOW, MEDIUM, HIGH


class PrivacyScanResponse(BaseModel):
    has_sensitive: bool
    risk_level: str             # NONE, LOW, MEDIUM, HIGH
    warnings: list[PrivacyEntity]
    # Prompt đã thay thế entity bằng [EMAIL], [PHONE]...
    anonymized_prompt: str
    safe_to_proceed: bool       # True nếu prompt sạch hoặc đã ẩn danh xong


class PrivacyResult(BaseModel):
    has_sensitive: bool
    risk_level: str
    warnings: List[PrivacyEntity]
    anonymized_prompt: str
    safe_to_proceed: bool

# ══════════════════════════════════════════════════════════════
#  S2 — PROMPT SCORING
# ══════════════════════════════════════════════════════════════


class ScoringRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=2000)
    domain: str = Field(...,
                        pattern=r"^(marketing|programming|writing|office|data|education)$")
    task_id: int = Field(..., gt=0)
    privacy_result: PrivacyScanResponse | None = None  # Kết quả S1 truyền vào


class CriterionScore(BaseModel):
    score: int
    max_score: int
    feedback: str


class ScoringResponse(BaseModel):
    total_score: int            # /100
    grade: str                  # A (90-100), B (70-89), C (50-69), D (<50)
    criteria: dict[str, CriterionScore]
    weak_criteria: list[str]    # Danh sách tiêu chí yếu nhất
    passed: bool                # True nếu >= 60


# ══════════════════════════════════════════════════════════════
#  S3 — PROMPT SUGGESTION
# ══════════════════════════════════════════════════════════════

class SuggestionRequest(BaseModel):
    anonymized_prompt: str = Field(..., min_length=10, max_length=2000)
    score_result: ScoringResponse
    domain: str
    task_id: int
    user_id: int


# Response là stream SSE — không có Pydantic model
# Từng chunk: "data: <token>\n\n", kết thúc: "data: [DONE]\n\n"


# ══════════════════════════════════════════════════════════════
#  S4 — QUIZ GENERATION
# ══════════════════════════════════════════════════════════════

class QuizGenRequest(BaseModel):
    lesson_content: str = Field(..., min_length=50, max_length=5000)
    num_questions: int = Field(default=5, ge=3, le=10)
    difficulty: str = Field(
        default="beginner", pattern=r"^(beginner|intermediate|advanced)$")
    question_types: list[str] = Field(default=["multiple_choice"])
    privacy_result: Optional[PrivacyResult] = None  # ← PHẢI CÓ DÒNG NÀY


class QuizQuestion(BaseModel):
    question: str
    options: list[str]          # 4 options cho multiple_choice
    correct_answer: str
    explanation: str


class QuizGenResponse(BaseModel):
    questions: list[QuizQuestion]
    lesson_summary: str


# ══════════════════════════════════════════════════════════════
#  S5 — LEARNING RECOMMENDATION
# ══════════════════════════════════════════════════════════════

class LearningRequest(BaseModel):
    user_id: int
    weak_criteria: list[str]
    domain: str
    user_level: str = Field(
        default="beginner", pattern=r"^(beginner|intermediate|advanced)$")
    recent_scores: list[int] = Field(default=[])


class LearningResponse(BaseModel):
    recommended_lesson_ids: list[int]
    tip: str
    example_prompt: str
    estimated_improvement: str


# ══════════════════════════════════════════════════════════════
#  S6 — PROGRESS ANALYSIS
# ══════════════════════════════════════════════════════════════

class ProgressRequest(BaseModel):
    user_id: int
    submissions_last_30_days: list[dict[str, Any]]
    quiz_results: list[dict[str, Any]]


class ProgressResponse(BaseModel):
    overall_trend: str          # "improving", "stable", "declining"
    strongest_criteria: list[str]
    weakest_criteria: list[str]
    average_score: float
    summary: str
    next_recommendation: str


# ══════════════════════════════════════════════════════════════
#  S7 — EXPERT REVIEW ASSIST
# ══════════════════════════════════════════════════════════════

class ExpertAssistRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)
    score_result: ScoringResponse
    domain: str
    task_description: str


class ExpertAssistResponse(BaseModel):
    draft_review: str
    suggested_score_adjustments: dict[str, int]
    flag: str | None            # None = OK, "FLAGGED: <reason>" = cần chú ý


# ══════════════════════════════════════════════════════════════
#  S8 — CONTENT MODERATION
# ══════════════════════════════════════════════════════════════

class ModerationRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)
    user_id: int


class ModerationResponse(BaseModel):
    is_safe: bool
    # hate, self_harm, violence, sexual, prompt_injection
    categories: dict[str, bool]
    flagged_reason: str | None
    action: str                  # "allow", "warn", "block"
