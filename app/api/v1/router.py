from fastapi import APIRouter
from app.api.v1.endpoints import (
    privacy,
    scoring,
    suggestion,
    quiz,
    learning,
    analysis,
    expert,
    moderation,
    health,
    admin,
    admin_dashboard
)

api_v1_router = APIRouter()

# ── Health (không cần auth — cho Docker healthcheck) ────────
api_v1_router.include_router(health.router, prefix="/health", tags=["Health"])

api_v1_router.include_router(admin.router, tags=["Admin"])  # ← THÊM DÒNG NÀY
api_v1_router.include_router(admin_dashboard.router, tags=["Admin Dashboard"])


# ── AI Services ──────────────────────────────────────────────
api_v1_router.include_router(
    privacy.router,    prefix="/privacy",    tags=["S1 Privacy Filter"])
api_v1_router.include_router(
    scoring.router,    prefix="/scoring",    tags=["S2 Prompt Scoring"])
api_v1_router.include_router(
    suggestion.router, prefix="/suggestion", tags=["S3 Suggestion"])
api_v1_router.include_router(
    quiz.router,       prefix="/quiz",       tags=["S4 Quiz Generation"])
api_v1_router.include_router(
    learning.router,   prefix="/learning",   tags=["S5 Learning Recommend"])
api_v1_router.include_router(
    analysis.router,   prefix="/analysis",   tags=["S6 Progress Analysis"])
api_v1_router.include_router(
    expert.router,     prefix="/expert",     tags=["S7 Expert Assist"])
api_v1_router.include_router(
    moderation.router, prefix="/moderation", tags=["S8 Moderation"])
