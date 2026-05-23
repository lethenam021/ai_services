"""
Moderation Service — Kiểm duyệt nội dung
Phát hiện nội dung nhạy cảm, vi phạm, spam, toxic
"""
import logging
import re
import hashlib
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.database import get_db
from app.db.entity.moderation_flag import ModerationFlag
from app.db.entity.usage_log import UsageLog
from app.db.entity.api_key import APIKey

router = APIRouter()
logger = logging.getLogger(__name__)


def truncate_json_str(data: str, max_length: int = 10000) -> str:
    """Truncate JSON string nếu quá dài"""
    if len(data) <= max_length:
        return data
    logger.warning(f"JSON data truncated: {len(data)} -> {max_length}")
    return data[:max_length]


# ============================================================
# Request/Response Models
# ============================================================
class ModerationRequest(BaseModel):
    content: str = Field(..., description="Nội dung cần kiểm duyệt",
                         min_length=1, max_length=10000)
    content_type: str = Field(
        "text", description="Loại nội dung: text, image, video")
    strictness: str = Field(
        "medium", description="Mức độ nghiêm ngặt: low, medium, high")
    check_categories: List[str] = Field(
        ["hate", "harassment", "violence", "self_harm", "sexual", "spam"],
        description="Các danh mục cần kiểm tra"
    )


class Violation(BaseModel):
    category: str
    severity: str
    description: str
    location: Optional[str] = None
    suggested_action: str


class ModerationResponse(BaseModel):
    success: bool
    is_approved: bool
    risk_score: float
    violations: List[Violation]
    flags: List[str]
    summary: str
    correlation_id: Optional[str] = None


# ============================================================
# Rule-based Moderation - Danh sách pattern đầy đủ
# ============================================================

SENSITIVE_PATTERNS = {
    # ========== HATE SPEECH (Ngôn ngữ thù địch) ==========
    "hate": {
        "patterns": [
            r"(đ[íi]t|ch[ế]t)( )?(m[ọa]|m[à]y|b[ọ]n|ch[ú]ng|n[ó])",
            r"(th[ằ]ng|con|đ[ồ])( )?(ch[ế]t|ng[u]|kh[ứ]ng|ch[ó]|l[ợ]n|kh[ỉ])",
            r"(d[â]y|ch[ú]c)( )?(d[ự]t|th[ù]|h[ậ]n)",
            r"ph[â]n( )?bi[ệ]t( )?ch[ủ]ng( )?t[ộ]c",
            r"c[ặ]c( )?(n[ứ]c|b[ầ]n|d[â]n)",
            r"đ[ệ] qu[ố]c( )?m[ỹ]",
            r"t[à]u( )?(kh[ỷ]|kh[ố]ng|ch[ế]t|c[ắ]t)",
            r"(th[ự]c( )?d[â]n|b[ọ]n( )?th[ự]c( )?d[â]n)",
            r"(x[ú]c( )?ph[ạ]m|s[ỉ])( )?(d[â]n|t[ộ]c|ng[ư]ời)",
        ],
        "severity": "high",
        "description": "Ngôn ngữ thù địch, kích động, phân biệt chủng tộc"
    },

    # ========== HARASSMENT (Quấy rối) ==========
    "harassment": {
        "patterns": [
            r"(m[à]y|th[ằ]ng|con)( )?(ch[ế]t|ng[u]|đ[ầ]n|kh[ứ]n|h[â]m)",
            r"(b[ế]n)( )?(l[ề]|th[ả]m|đ[ộ]i)",
            r"l[ũ]( )?(ch[ế]t|ng[u]|kh[ứ]n|s[â]u|b[ọ]i)",
            r"(r[ả]nh|r[ỗ]i)( )?(ch[ứ]|h[ả]|qu[á]|l[ê]n)",
            r"(th[ằ]ng|con)( )?(h[ề]|h[è]|h[ạ]i)",
            r"(ng[u]|d[ố]t|k[é]m)( )?(c[ỏ]i|i[ế]t|n[ă]ng|l[ự]c)",
            r"(v[ô]( )?d[ụ]ng|ch[ẳ]ng( )?ra( )?g[ì])",
            r"(ch[ế]t( )?n[à]o|ch[ế]t( )?đ[ê]n|ch[ế]t( )?b[ằ]n)",
        ],
        "severity": "medium",
        "description": "Quấy rối, xúc phạm cá nhân, lăng mạ"
    },

    # ========== VIOLENCE (Bạo lực) - CẢI THIỆN ==========
    "violence": {
        "patterns": [
            # Hành vi bạo lực trực tiếp
            r"gi[ế]t",
            r"ch[é]m",
            r"đ[ậ]p",
            r"đ[á]nh",
            r"s[á]t( )?h[ạ]i",
            r"t[à]n( )?s[á]t",
            r"b[ạ]o( )?h[à]nh",
            r"x[ô]( )?x[á]t",
            r"t[ư][ơ]ng( )?t[à]n",

            # Bạo lực có đối tượng
            r"gi[ế]t( )?(ng[ư]ời|m[à]y|tao|n[ó]|h[ắ]n|b[ọ]n|ch[ú]ng)",
            r"ch[é]m( )?(ng[ư]ời|m[à]y|tao|n[ó]|h[ắ]n)",
            r"đ[ậ]p( )?(ng[ư]ời|m[à]y|tao|n[ó]|h[ắ]n|v[ỡ]|tan)",
            r"đ[á]nh( )?(ng[ư]ời|m[à]y|tao|n[ó]|h[ắ]n|g[ã]y|ch[ế]t)",
            r"t[ấ]n( )?c[ô]ng( )?(ng[ư]ời|m[à]y|tao|n[ó])",

            # Vũ khí / bạo lực nói chung
            r"b[ạ]o( )?l[ự]c",
            r"v[ũ]( )?kh[í]",
            r"s[ú]ng",
            r"ph[á]( )?ho[ạ]i",
            r"th[ư][ơ]ng( )?t[í]ch",
            r"đ[ổ]( )?m[á]u",
            r"th[à]m( )?s[á]t",

            # Cụm từ đe dọa
            r"cho( )?(m[à]y|tao|n[ó])( )?m[ộ]t( )?b[à]i( )?h[ọ]c",
            r"(kh[ô]ng)( )?tha( )?th[ứ]",
            r"x[ử] l[ý]",
            r"d[ạ]y( )?cho( )?m[à]y( )?m[ộ]t( )?b[à]i",
        ],
        "severity": "high",
        "description": "Nội dung bạo lực, đe dọa, bạo hành"
    },

    # ========== SELF HARM (Tự hại) ==========
    "self_harm": {
        "patterns": [
            r"t[ự]( )?t[ử]",
            r"mu[ố]n( )?ch[ế]t",
            r"ch[ế]t( )?đi",
            r"k[ế]t( )?th[ú]c( )?cu[ộ]c( )?đ[ờ]i",
            r"l[à]m( )?h[ạ]i( )?b[ả]n( )?th[â]n",
            r"c[ắ]t( )?t[â]y",
            r"c[ắ]t( )?t[a]y",
            r"kh[ô]ng( )?mu[ố]n( )?s[ố]ng",
            r"k[ế]t( )?li[ễ]u",
            r"quy[ê]n( )?sinh",
        ],
        "severity": "high",
        "description": "Nội dung về tự hại, tự tử, ý định kết liễu"
    },

    # ========== SEXUAL CONTENT (Tình dục) ==========
    "sexual": {
        "patterns": [
            r"sex",
            r"d[â]m",
            r"đ[ụ]",
            r"b[ú]",
            r"l[ồ]n",
            r"v[ú]",
            r"c[ặ]c",
            r"bu[ồ]i",
            r"khi[ê]u( )?d[â]m",
            r"n[ộ]i( )?dung( )?ng[ư]ời( )?l[ớ]n",
            r"l[à]m( )?t[ì]nh",
            r"quan( )?h[ệ]( )?t[ì]nh( )?d[ụ]c",
            r"porn",
            r"kh[ỏ]a( )?th[â]n",
            r"nh[ạ]y( )?c[ả]m",
        ],
        "severity": "high",
        "description": "Nội dung tình dục, khiêu dâm, 18+"
    },

    # ========== SPAM (Thư rác) ==========
    "spam": {
        "patterns": [
            r"(\b\w+\b\s*){20,}",           # Quá nhiều từ (>20)
            r"(https?://[^\s]+){3,}",        # Nhiều link (>3)
            r"(\b\w+\b\s*){1,}\1{4,}",      # Lặp từ (>4 lần)
            r"mua( )?ngay",
            r"gi[ả]m( )?gi[á]",
            r"khuy[ế]n( )?m[ạ]i",
            r"[0-9]{3,}%.*?gi[ả]m",
        ],
        "severity": "low",
        "description": "Nội dung spam, quảng cáo rác, tiếp thị quá mức"
    },
}

# Từ khóa an toàn (miễn trừ)
SAFE_PATTERNS = [
    r"h[ọ]c( )?(ai|m[á]y( )?t[í]nh|l[ậ]p( )?tr[ì]nh|python|java|javascript)",
    r"gi[ả]i( )?th[í]ch( )?(kh[á]i( )?ni[ệ]m|thu[ậ]t( )?to[á]n|b[à]i( )?t[ậ]p)",
    r"b[à]i( )?t[ậ]p( )?(python|java|c[+][+]|javascript|html|css)",
    r"l[ộ]( )?tr[ì]nh( )?h[ọ]c( )?(ai|ml|ds|data( )?science)",
    r"c[â]u( )?h[Ỏ]i( )?(ph[ỏ]ng( )?v[ấ]n|thi( )?c[ử]|tr[ắ]c( )?nghi[ệ]m)",
    r"t[à]i( )?li[ệ]u( )?h[ọ]c( )?t[ậ]p",
    r"kh[ó]a( )?h[ọ]c( )?(ai|ml|dl|python)",
]


def moderate_text(content: str, categories: List[str], strictness: str) -> tuple[List[Violation], float, List[str]]:
    """
    Kiểm duyệt nội dung text bằng rule-based
    Returns: (violations, risk_score, flags)
    """
    violations = []
    flags = []
    content_lower = content.lower()

    # Điều chỉnh ngưỡng theo strictness
    threshold_map = {"low": 0.7, "medium": 0.5, "high": 0.3}

    # Kiểm tra nội dung học tập (được miễn trừ)
    is_educational = False
    for safe_pattern in SAFE_PATTERNS:
        if re.search(safe_pattern, content_lower, re.IGNORECASE):
            is_educational = True
            flags.append("educational_content")
            break

    # Nếu là nội dung học tập và strictness thấp, bỏ qua kiểm duyệt
    if is_educational and strictness == "low":
        return [], 5.0, ["educational_content"]

    # Kiểm tra từng category
    for category in categories:
        if category not in SENSITIVE_PATTERNS:
            continue

        pattern_config = SENSITIVE_PATTERNS[category]
        matched_patterns = []

        for pattern in pattern_config["patterns"]:
            try:
                matches = re.findall(pattern, content_lower,
                                     re.IGNORECASE | re.UNICODE)
                if matches:
                    matched_patterns.extend(matches)
                    logger.info(f"Matched {category}: {pattern} -> {matches}")
            except re.error as e:
                logger.warning(f"Regex error for pattern {pattern}: {e}")
                continue

        if matched_patterns:
            # Tính severity
            severity = pattern_config["severity"]
            if strictness == "high" and severity == "medium":
                severity = "high"
            elif strictness == "low" and severity == "high":
                severity = "medium"

            violations.append(Violation(
                category=category,
                severity=severity,
                description=pattern_config["description"],
                location=f"Phát hiện {len(matched_patterns)} từ khóa vi phạm",
                suggested_action="Xóa hoặc chỉnh sửa nội dung vi phạm"
            ))
            flags.append(f"{category}_detected")

    # Tính risk_score dựa trên violations
    if violations:
        # Tính điểm dựa trên số lượng và severity
        base_score = 50
        high_count = sum(1 for v in violations if v.severity == "high")
        medium_count = sum(1 for v in violations if v.severity == "medium")

        risk_score = base_score + (high_count * 20) + (medium_count * 10)
        risk_score = min(100, risk_score)
    else:
        risk_score = 10.0

    # Điều chỉnh theo strictness
    if strictness == "high":
        risk_score = min(100, risk_score + 15)
    elif strictness == "low":
        risk_score = max(0, risk_score - 15)

    return violations, risk_score, flags


# ============================================================
# Main Endpoint
# ============================================================
@router.post("/check", response_model=ModerationResponse)
async def check_content(
    request: Request,
    payload: ModerationRequest,
    db: AsyncSession = Depends(get_db)
):
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    logger.info(
        f"[{correlation_id}] Moderation request: type={payload.content_type}, strictness={payload.strictness}")

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

    start_time = datetime.utcnow()

    try:
        if payload.content_type == "text":
            violations, risk_score, flags = moderate_text(
                payload.content, payload.check_categories, payload.strictness
            )
        elif payload.content_type == "image":
            violations, risk_score, flags = [], 5.0, ["image_not_analyzed"]
        elif payload.content_type == "video":
            violations, risk_score, flags = [], 5.0, ["video_not_analyzed"]
        else:
            raise ValueError(
                f"Unsupported content_type: {payload.content_type}")

        is_approved = risk_score < 50

        if is_approved:
            summary = "✅ Nội dung an toàn, có thể duyệt."
        else:
            violation_categories = list(set(v.category for v in violations))
            summary = f"⚠️ Nội dung vi phạm: {', '.join(violation_categories)}. Risk score: {risk_score:.1f}%"
            if violations and not is_approved:
                summary += " Vui lòng chỉnh sửa nội dung trước khi gửi lại."

        # Lưu vào database
        content_hash = hashlib.md5(payload.content.encode()).hexdigest()
        flag = ModerationFlag(
            user_id=user_id,
            correlation_id=correlation_id,
            content_hash=content_hash,
            content=payload.content[:2000],
            categories=[v.category for v in violations],
            risk_score=risk_score,
            action_taken="block" if not is_approved else "allow"
        )
        db.add(flag)

        latency_ms = int(
            (datetime.utcnow() - start_time).total_seconds() * 1000)
        usage_log = UsageLog(
            correlation_id=correlation_id,
            user_id=user_id,
            api_key_id=api_key_id,
            service_name="moderation",
            request_data=truncate_json_str(payload.model_dump_json()),
            response_data=truncate_json_str(json.dumps(
                {"is_approved": is_approved, "risk_score": risk_score})),
            prompt_tokens=len(payload.content.split()),
            completion_tokens=len(violations),
            latency_ms=latency_ms,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent[:500]
        )
        db.add(usage_log)
        await db.commit()

        logger.info(
            f"[{correlation_id}] Moderation result: approved={is_approved}, risk={risk_score}, violations={len(violations)}")

        return ModerationResponse(
            success=True,
            is_approved=is_approved,
            risk_score=round(risk_score, 1),
            violations=violations,
            flags=flags,
            summary=summary,
            correlation_id=correlation_id
        )

    except Exception as e:
        logger.error(f"[{correlation_id}] Moderation error: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "MOD_001",
                "message": f"Failed to moderate content: {str(e)}",
                "correlation_id": correlation_id
            }
        )


# ============================================================
# Batch Moderation
# ============================================================
class BatchModerationRequest(BaseModel):
    contents: List[str] = Field(...,
                                description="Danh sách nội dung cần kiểm duyệt")
    strictness: str = Field("medium", description="Mức độ nghiêm ngặt")


class BatchModerationResponse(BaseModel):
    success: bool
    results: List[ModerationResponse]
    summary: Dict[str, Any]
    correlation_id: Optional[str] = None


@router.post("/batch", response_model=BatchModerationResponse)
async def batch_check_content(request: Request, payload: BatchModerationRequest):
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    results = []
    approved_count = 0
    rejected_count = 0

    for content in payload.contents:
        violations, risk_score, flags = moderate_text(
            content, ["hate", "harassment",
                      "violence", "spam"], payload.strictness
        )
        is_approved = risk_score < 50
        if is_approved:
            approved_count += 1
        else:
            rejected_count += 1

        results.append(ModerationResponse(
            success=True,
            is_approved=is_approved,
            risk_score=round(risk_score, 1),
            violations=violations,
            flags=flags,
            summary=f"Risk score: {risk_score:.1f}%",
            correlation_id=correlation_id
        ))

    return BatchModerationResponse(
        success=True,
        results=results,
        summary={
            "total": len(payload.contents),
            "approved": approved_count,
            "rejected": rejected_count,
            "approval_rate": round(approved_count / len(payload.contents) * 100, 1)
        },
        correlation_id=correlation_id
    )


@router.get("/categories")
async def get_categories():
    """Lấy danh sách các danh mục kiểm duyệt"""
    return {
        "categories": list(SENSITIVE_PATTERNS.keys()),
        "descriptions": {k: v["description"] for k, v in SENSITIVE_PATTERNS.items()},
        "severity_levels": {k: v["severity"] for k, v in SENSITIVE_PATTERNS.items()}
    }


@router.get("/health")
async def health_check():
    return {"service": "moderation", "status": "healthy"}
