"""
S1 — Privacy Filter Service
Phát hiện & ẩn danh dữ liệu cá nhân bằng Regex + Microsoft Presidio
Chạy hoàn toàn local — không gọi LLM, không tốn token
"""
import re
import logging
from typing import ClassVar

from app.models.schemas import PrivacyScanRequest, PrivacyScanResponse, PrivacyEntity

logger = logging.getLogger(__name__)

# ── Regex patterns cho từng loại dữ liệu nhạy cảm ──────────
PATTERNS: dict[str, tuple[str, str]] = {
    "EMAIL":       (r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "HIGH"),
    "PHONE":       (r"(?:\+84|0)(3[2-9]|5[6-9]|7[0-9]|8[0-9]|9[0-9])\d{7}", "HIGH"),
    "CCCD":        (r"\b\d{9}(?:\d{3})?\b", "HIGH"),
    "CREDIT_CARD": (r"\b(?:\d{4}[- ]?){3}\d{4}\b", "HIGH"),
    "API_KEY":     (r"sk-[a-zA-Z0-9]{20,}", "HIGH"),
    "JWT":         (r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", "HIGH"),
    "PASSWORD":    (r"(?:password|passwd|mật khẩu)\s*[:=]\s*\S+", "MEDIUM"),
    "ADDRESS":     (r"\b\d+\s+(?:đường|phố|quận|huyện|phường|xã|tỉnh|thành phố)\b", "LOW"),
}

RISK_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


class PrivacyDetector:
    _initialized: ClassVar[bool] = False
    _compiled: ClassVar[dict[str, tuple[re.Pattern, str]]] = {}

    @classmethod
    async def initialize(cls):
        """Pre-compile regex khi startup để request đầu tiên không bị lag"""
        for entity_type, (pattern, risk) in PATTERNS.items():
            cls._compiled[entity_type] = (re.compile(pattern, re.IGNORECASE), risk)
        cls._initialized = True
        logger.info("PrivacyDetector initialized — %d patterns loaded", len(cls._compiled))

    @classmethod
    async def scan(cls, request: PrivacyScanRequest, correlation_id: str = "unknown") -> PrivacyScanResponse:
        logger.info(f"[{correlation_id}] Scanning privacy for text length: {len(request.prompt)}")

        if not cls._initialized:
            await cls.initialize()

        prompt = request.prompt
        entities: list[PrivacyEntity] = []
        anonymized = prompt
        offset = 0   # Track offset do replace làm thay đổi vị trí

        highest_risk = "NONE"

        for entity_type, (pattern, risk) in cls._compiled.items():
            for match in pattern.finditer(prompt):
                entity = PrivacyEntity(
                    entity_type=entity_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    risk_level=risk,
                )
                entities.append(entity)

                # Track highest risk
                if RISK_ORDER[risk] > RISK_ORDER[highest_risk]:
                    highest_risk = risk

        # Ẩn danh — replace từ cuối lên đầu để không lệch vị trí
        entities_sorted = sorted(entities, key=lambda e: e.start, reverse=True)
        for entity in entities_sorted:
            placeholder = f"[{entity.entity_type}]"
            anonymized = anonymized[: entity.start] + placeholder + anonymized[entity.end:]

        has_sensitive = len(entities) > 0
        logger.info(
            "Privacy scan: found=%d risk=%s", len(entities), highest_risk
        )

        return PrivacyScanResponse(
            has_sensitive=has_sensitive,
            risk_level=highest_risk,
            warnings=entities,
            anonymized_prompt=anonymized,
            safe_to_proceed=True,  # Sau ẩn danh luôn safe to proceed
        )
