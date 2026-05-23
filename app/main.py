"""
Bình Dân Học AI — FastAPI AI Services Layer
Entry point chính
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.config import settings
from app.middleware.auth import InternalAuthMiddleware
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.api.v1.router import api_v1_router
from app.api.v1.endpoints import admin_dashboard
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & Shutdown lifecycle"""
    from app.services.privacy.detector import PrivacyDetector
    await PrivacyDetector.initialize()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bình Dân Học AI — AI Services",
        version="1.0.0",
        description="Internal AI Services Layer — Not for public access",
        docs_url="/docs",  # Bật Swagger UI trên mọi môi trường
        redoc_url=None,
        lifespan=lifespan,
    )

    # Middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
    )
    app.add_middleware(InternalAuthMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # Routes
    app.include_router(admin_dashboard.router, tags=["Admin Dashboard"])
    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()


# ============================================================
# Custom OpenAPI để thêm nút Authorize vào Swagger UI
# ============================================================
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Internal-Key",
            "description": "Nhập API key: **bdh-internal-key-2024**"
        }
    }

    openapi_schema["security"] = [{"APIKeyHeader": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
