"""
Progress Analysis Service — Phân tích tiến trình học tập của người dùng
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.utils.usage_logger import log_api_usage

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# Request/Response Models
# ============================================================
class ProgressAnalysisRequest(BaseModel):
    user_id: str = Field(..., description="ID của người dùng")
    time_range: str = Field("month", description="Khoảng thời gian: week, month, quarter, year")
    metrics: List[str] = Field(["accuracy", "completion_rate"], description="Các chỉ số cần phân tích")
    include_details: bool = Field(True, description="Bao gồm chi tiết hay không")


class MetricData(BaseModel):
    name: str
    current_value: float
    previous_value: float
    trend: str  # up, down, stable
    improvement: float  # phần trăm thay đổi
    history: Optional[List[float]] = None


class ProgressAnalysisResponse(BaseModel):
    success: bool
    user_id: str
    time_range: str
    summary: Dict[str, Any]
    metrics: List[MetricData]
    recommendations: List[str]
    correlation_id: Optional[str] = None


# ============================================================
# Mock Data (sau này thay bằng database thật)
# ============================================================
async def get_user_learning_data(user_id: str, time_range: str) -> Dict[str, Any]:
    """Lấy dữ liệu học tập của user (mock data)"""
    
    # Mock data cho các chỉ số
    mock_data = {
        "accuracy": {
            "current": 85.5,
            "previous": 78.2,
            "history": [72, 75, 78, 80, 82, 84, 85.5]
        },
        "completion_rate": {
            "current": 92.0,
            "previous": 88.5,
            "history": [80, 83, 86, 88, 90, 91, 92]
        },
        "time_spent": {
            "current": 120,  # phút/ngày
            "previous": 95,
            "history": [80, 85, 90, 95, 105, 115, 120]
        },
        "quiz_score": {
            "current": 78.5,
            "previous": 72.0,
            "history": [65, 68, 70, 72, 75, 77, 78.5]
        },
        "engagement": {
            "current": 88.0,
            "previous": 82.0,
            "history": [75, 78, 80, 82, 85, 87, 88]
        }
    }
    
    return mock_data


async def generate_recommendations(metrics: List[MetricData]) -> List[str]:
    """Tạo gợi ý dựa trên các chỉ số"""
    recommendations = []
    
    for metric in metrics:
        if metric.name == "accuracy" and metric.trend == "down":
            recommendations.append("📚 Độ chính xác đang giảm. Hãy ôn lại kiến thức cơ bản và làm thêm bài tập.")
        elif metric.name == "accuracy" and metric.current_value < 70:
            recommendations.append("⚠️ Độ chính xác dưới 70%. Nên xem lại video bài giảng và tham khảo thêm tài liệu.")
        elif metric.name == "accuracy" and metric.current_value > 85:
            recommendations.append("🎉 Độ chính xác tốt! Hãy thử thách bản thân với bài tập nâng cao.")
            
        if metric.name == "completion_rate" and metric.trend == "down":
            recommendations.append("⏰ Tỷ lệ hoàn thành đang giảm. Hãy chia nhỏ mục tiêu học tập hàng ngày.")
        elif metric.name == "completion_rate" and metric.current_value < 70:
            recommendations.append("⚠️ Tỷ lệ hoàn thành thấp. Đặt lịch học cố định mỗi ngày 30 phút.")
            
        if metric.name == "time_spent" and metric.current_value < 60:
            recommendations.append("⏱️ Thời gian học ít. Cố gắng dành ít nhất 1 giờ mỗi ngày để học.")
            
        if metric.name == "quiz_score" and metric.current_value < 70:
            recommendations.append("📝 Điểm quiz thấp. Làm lại các câu hỏi sai và học theo chủ đề.")
    
    if not recommendations:
        recommendations.append("✅ Tiến trình tốt! Hãy duy trì và thử thách với nội dung nâng cao hơn.")
    
    return recommendations[:5]  # Tối đa 5 gợi ý


# ============================================================
# Main Endpoint
# ============================================================
@router.post("/progress", response_model=ProgressAnalysisResponse)
async def analyze_progress(request: Request, payload: ProgressAnalysisRequest):
    """
    Phân tích tiến trình học tập của người dùng
    
    - **user_id**: ID của người dùng
    - **time_range**: Khoảng thời gian (week, month, quarter, year)
    - **metrics**: Các chỉ số cần phân tích (accuracy, completion_rate, time_spent, quiz_score, engagement)
    - **include_details**: Có trả về chi tiết lịch sử hay không
    """
    
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    logger.info(f"[{correlation_id}] Analyzing progress for user {payload.user_id}")
    
    try:
        # Lấy dữ liệu học tập
        learning_data = await get_user_learning_data(payload.user_id, payload.time_range)
        
        # Xây dựng metrics
        metrics_data = []
        for metric_name in payload.metrics:
            if metric_name not in learning_data:
                continue
                
            data = learning_data[metric_name]
            current = data["current"]
            previous = data["previous"]
            
            # Tính trend
            if current > previous:
                trend = "up"
            elif current < previous:
                trend = "down"
            else:
                trend = "stable"
            
            # Tính phần trăm cải thiện
            improvement = ((current - previous) / previous * 100) if previous > 0 else 0
            
            metric = MetricData(
                name=metric_name,
                current_value=round(current, 1),
                previous_value=round(previous, 1),
                trend=trend,
                improvement=round(improvement, 1),
                history=data["history"] if payload.include_details else None
            )
            metrics_data.append(metric)
        
        # Tóm tắt tổng quan
        avg_improvement = sum([m.improvement for m in metrics_data]) / len(metrics_data) if metrics_data else 0
        improving_count = len([m for m in metrics_data if m.trend == "up"])
        
        summary = {
            "total_metrics": len(metrics_data),
            "improving_metrics": improving_count,
            "declining_metrics": len([m for m in metrics_data if m.trend == "down"]),
            "avg_improvement_pct": round(avg_improvement, 1),
            "overall_trend": "improving" if improving_count > len(metrics_data)/2 else "needs_attention",
            "analysis_period": payload.time_range
        }
        
        # Tạo gợi ý
        recommendations = await generate_recommendations(metrics_data)
        
        # Log kết quả
        await log_api_usage(
            correlation_id=correlation_id,
            user_id=int(payload.user_id) if payload.user_id.isdigit() else 0,
            service_name="progress_analysis",
            model="rule_based",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            status="success"
        )
        
        return ProgressAnalysisResponse(
            success=True,
            user_id=payload.user_id,
            time_range=payload.time_range,
            summary=summary,
            metrics=metrics_data,
            recommendations=recommendations,
            correlation_id=correlation_id
        )
        
    except Exception as e:
        logger.error(f"[{correlation_id}] Progress analysis error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "ANALYSIS_001",
                "message": f"Failed to analyze progress: {str(e)}",
                "correlation_id": correlation_id
            }
        )


# ============================================================
# Health Check cho service này
# ============================================================
@router.get("/health")
async def health_check():
    return {"service": "progress_analysis", "status": "healthy"}