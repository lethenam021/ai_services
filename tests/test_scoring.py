import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_scoring_bad_prompt():
    """Test scoring with bad prompt (low score)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/scoring/evaluate",
            json={
                "prompt": "viết content",
                "domain": "marketing",
                "task_id": 1
            },
            headers={"X-Internal-Key": "bdh-internal-key-2024"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_score" in data
        assert "grade" in data
        assert "weak_criteria" in data
        assert data["total_score"] < 60


@pytest.mark.asyncio
async def test_scoring_good_prompt():
    """Test scoring with good prompt (high score)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/scoring/evaluate",
            json={
                "prompt": "Bạn là chuyên gia marketing. Hãy viết bài quảng cáo về khóa học AI dành cho người mới bắt đầu. Bài viết dài 200-300 từ, phong cách thân thiện.",
                "domain": "marketing",
                "task_id": 1
            },
            headers={"X-Internal-Key": "bdh-internal-key-2024"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_score"] > 50


@pytest.mark.asyncio
async def test_scoring_short_prompt():
    """Test scoring with very short prompt (should fail validation)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/scoring/evaluate",
            json={
                "prompt": "test",
                "domain": "marketing",
                "task_id": 1
            },
            headers={"X-Internal-Key": "bdh-internal-key-2024"}
        )
        # Prompt quá ngắn (<10 ký tự) nên trả về 422
        assert response.status_code == 422