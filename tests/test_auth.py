import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_missing_api_key():
    """Test endpoint without API key"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/scoring/evaluate",
            json={
                "prompt": "Viết content marketing",
                "domain": "marketing",
                "task_id": 1
            }
            # Không có header X-Internal-Key
        )
        assert response.status_code == 401
        data = response.json()
        assert "error_code" in data


@pytest.mark.asyncio
async def test_invalid_api_key():
    """Test endpoint with invalid API key"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/scoring/evaluate",
            json={
                "prompt": "Viết content marketing",
                "domain": "marketing",
                "task_id": 1
            },
            headers={"X-Internal-Key": "invalid-key-123"}
        )
        assert response.status_code == 401