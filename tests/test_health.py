import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint (cần auth)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/health",
            # ← THÊM DÒNG NÀY
            headers={"X-Internal-Key": "bdh-internal-key-2024"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "version" in data
