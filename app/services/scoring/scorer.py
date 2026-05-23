"""
S2 — Prompt Scoring Service
Chấm điểm theo 8 tiêu chí — Rule-based, không gọi LLM
Trả kết quả trong < 200ms
"""
import re
import logging
from datetime import datetime
from typing import Optional
from app.models.schemas import ScoringRequest, ScoringResponse, CriterionScore

logger = logging.getLogger(__name__)

# ── Keyword banks cho từng tiêu chí ─────────────────────────
ROLE_KEYWORDS = [
    "bạn là", "với tư cách", "đóng vai", "hãy đóng vai",
    "you are", "act as", "as a", "as an expert",
    "với vai trò", "trong vai trò",
]
FORMAT_KEYWORDS = [
    "bảng", "danh sách", "list", "table", "json", "markdown",
    "đoạn văn", "bullet", "checklist", "dàn ý", "outline",
    "format", "định dạng", "trình bày theo",
]
CONTEXT_KEYWORDS = [
    "bối cảnh", "ngữ cảnh", "tình huống", "background",
    "context", "trong trường hợp", "khi mà", "hiện tại",
    "dự án", "công ty", "khách hàng",
]
AUDIENCE_KEYWORDS = [
    "đối với", "cho", "dành cho", "người đọc", "audience",
    "khách hàng", "sinh viên", "học sinh", "người mới",
    "target", "độc giả", "người dùng",
]
CONSTRAINT_KEYWORDS = [
    "tối đa", "không quá", "ngắn gọn", "chi tiết",
    "bằng tiếng", "in english", "trong vòng",
    "giới hạn", "limit", "phong cách", "tone",
    "formal", "informal", "chuyên nghiệp",
]


def _has_keywords(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def _word_count(text: str) -> int:
    return len(text.split())


def _score_task(prompt: str) -> CriterionScore:
    """Nhiệm vụ — Prompt có nêu rõ cần làm gì không?"""
    action_verbs = ["viết", "tạo", "phân tích", "giải thích", "tóm tắt",
                    "dịch", "liệt kê", "so sánh", "đề xuất", "hãy",
                    "write", "create", "analyze", "explain", "summarize"]
    has_action = _has_keywords(prompt, action_verbs)
    word_count = _word_count(prompt)

    if has_action and word_count >= 20:
        return CriterionScore(score=15, max_score=15, feedback="Nhiệm vụ rõ ràng và cụ thể")
    elif has_action:
        return CriterionScore(score=10, max_score=15, feedback="Có nhiệm vụ nhưng prompt còn ngắn, cần thêm chi tiết")
    else:
        return CriterionScore(score=4, max_score=15, feedback="Chưa nêu rõ nhiệm vụ cần AI thực hiện")


def _score_context(prompt: str) -> CriterionScore:
    has_ctx = _has_keywords(prompt, CONTEXT_KEYWORDS)
    word_count = _word_count(prompt)
    if has_ctx and word_count >= 30:
        return CriterionScore(score=15, max_score=15, feedback="Ngữ cảnh đầy đủ")
    elif has_ctx or word_count >= 25:
        return CriterionScore(score=9, max_score=15, feedback="Có ngữ cảnh nhưng chưa đủ cụ thể")
    else:
        return CriterionScore(score=4, max_score=15, feedback="Thiếu ngữ cảnh — AI không biết tình huống của bạn")


def _score_role(prompt: str) -> CriterionScore:
    if _has_keywords(prompt, ROLE_KEYWORDS):
        return CriterionScore(score=10, max_score=10, feedback="Đã xác định vai trò rõ ràng")
    return CriterionScore(score=3, max_score=10, feedback="Chưa giao vai trò cho AI (ví dụ: 'Bạn là chuyên gia marketing')")


def _score_audience(prompt: str) -> CriterionScore:
    if _has_keywords(prompt, AUDIENCE_KEYWORDS):
        return CriterionScore(score=10, max_score=10, feedback="Đã xác định đối tượng mục tiêu")
    return CriterionScore(score=3, max_score=10, feedback="Chưa xác định ai sẽ đọc kết quả")


def _score_format(prompt: str) -> CriterionScore:
    if _has_keywords(prompt, FORMAT_KEYWORDS):
        return CriterionScore(score=15, max_score=15, feedback="Yêu cầu định dạng rõ ràng")
    return CriterionScore(score=4, max_score=15, feedback="Chưa yêu cầu định dạng đầu ra (bảng, danh sách, JSON...)")


def _score_constraint(prompt: str) -> CriterionScore:
    if _has_keywords(prompt, CONSTRAINT_KEYWORDS):
        return CriterionScore(score=10, max_score=10, feedback="Có ràng buộc cụ thể")
    return CriterionScore(score=4, max_score=10, feedback="Chưa có ràng buộc về độ dài, ngôn ngữ hoặc phong cách")


def _score_feasibility(prompt: str) -> CriterionScore:
    word_count = _word_count(prompt)
    if word_count < 5:
        return CriterionScore(score=3, max_score=15, feedback="Prompt quá ngắn, không thể thực hiện hiệu quả")
    if word_count > 400:
        return CriterionScore(score=10, max_score=15, feedback="Prompt khá dài, cân nhắc chia nhỏ thành nhiều prompt")
    return CriterionScore(score=15, max_score=15, feedback="Độ dài và phạm vi hợp lý")


def _score_safety(privacy_result) -> CriterionScore:
    if privacy_result is None or not privacy_result.has_sensitive:
        return CriterionScore(score=10, max_score=10, feedback="Không phát hiện dữ liệu cá nhân")
    risk = privacy_result.risk_level
    if risk == "HIGH":
        return CriterionScore(score=0, max_score=10, feedback=f"Phát hiện {len(privacy_result.warnings)} thông tin nhạy cảm mức cao")
    elif risk == "MEDIUM":
        return CriterionScore(score=4, max_score=10, feedback="Có thông tin nhạy cảm mức trung bình")
    return CriterionScore(score=7, max_score=10, feedback="Có thông tin nhạy cảm mức thấp đã được ẩn danh")


GRADE_MAP = [(90, "A"), (70, "B"), (50, "C"), (0, "D")]


class PromptScorer:
    @staticmethod
    async def evaluate(
        request: ScoringRequest,
        correlation_id: str = "unknown",
        user_id: Optional[int] = None  # optional user id
    ) -> ScoringResponse:
        """Chấm điểm prompt và trả về kết quả"""

        logger.info(
            f"[{correlation_id}] Scoring prompt for user {user_id}, length: {len(request.prompt)}")

        prompt = request.prompt
        criteria = {
            "task":        _score_task(prompt),
            "context":     _score_context(prompt),
            "role":        _score_role(prompt),
            "audience":    _score_audience(prompt),
            "format":      _score_format(prompt),
            "constraint":  _score_constraint(prompt),
            "feasibility": _score_feasibility(prompt),
            "safety":      _score_safety(request.privacy_result),
        }

        total = sum(c.score for c in criteria.values())
        grade = next(g for threshold, g in GRADE_MAP if total >= threshold)
        weak = [k for k, v in criteria.items() if v.score / v.max_score < 0.5]

        logger.info(
            f"[{correlation_id}] Scoring result: total={total}, grade={grade}, weak={weak}")

        return ScoringResponse(
            total_score=total,
            grade=grade,
            criteria=criteria,
            weak_criteria=weak,
            passed=total >= 60,
        )
