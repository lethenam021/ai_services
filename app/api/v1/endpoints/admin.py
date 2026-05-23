from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.db.database import get_db
from app.db.entity.user import User
from app.db.entity.api_key import APIKey
from app.db.entity.usage_log import UsageLog
from pydantic import BaseModel
import uuid
from datetime import datetime, timedelta

router = APIRouter(prefix="/admin", tags=["Admin"])


class UserCreate(BaseModel):
    username: str
    email: str


class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    is_active: bool | None = None


# ========== USER MANAGEMENT ==========

@router.post("/users")
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    """Tạo user mới"""
    # Kiểm tra username đã tồn tại chưa
    result = await db.execute(select(User).where(User.username == user.username))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Username already exists")

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password="temporary",  # TODO: hash thật
        is_active=True
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username, "email": new_user.email}


@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """Lấy danh sách users (phân trang)"""
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    return {
        "total": len(users),
        "users": [{"id": u.id, "username": u.username, "email": u.email, "is_active": u.is_active} for u in users]
    }


@router.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Lấy thông tin chi tiết user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return {"id": user.id, "username": user.username, "email": user.email, "is_active": user.is_active}


@router.put("/users/{user_id}")
async def update_user(user_id: int, user_update: UserUpdate, db: AsyncSession = Depends(get_db)):
    """Cập nhật user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    if user_update.username is not None:
        user.username = user_update.username
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.is_active is not None:
        user.is_active = user_update.is_active

    await db.commit()
    return {"id": user.id, "username": user.username, "email": user.email, "is_active": user.is_active}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Xoá user (vô hiệu hoá, không xoá cứng)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    user.is_active = False
    await db.commit()
    return {"message": f"User {user_id} deactivated"}


# ========== API KEY MANAGEMENT ==========

@router.post("/users/{user_id}/api-keys")
async def create_api_key(user_id: int, db: AsyncSession = Depends(get_db)):
    """Tạo API key mới cho user"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if not user.is_active:
        raise HTTPException(400, "User is inactive")

    new_key = APIKey(
        key=f"bdh_{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        name=f"Key for {user.username}",
        expires_at=datetime.utcnow() + timedelta(days=90),
        is_active=True
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return {
        "id": new_key.id,
        "api_key": new_key.key,
        "expires_at": new_key.expires_at,
        "message": "Save this key! It will not be shown again."
    }


@router.get("/api-keys")
async def list_api_keys(
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Lấy danh sách API keys (lọc theo user_id nếu có)"""
    if user_id:
        result = await db.execute(select(APIKey).where(APIKey.user_id == user_id))
    else:
        result = await db.execute(select(APIKey))
    keys = result.scalars().all()
    return {
        "api_keys": [
            {
                "id": k.id,
                "user_id": k.user_id,
                "name": k.name,
                "expires_at": k.expires_at,
                "is_active": k.is_active,
                "last_used_at": k.last_used_at
            } for k in keys
        ]
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: int, db: AsyncSession = Depends(get_db)):
    """Thu hồi API key (vô hiệu hoá)"""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(404, "API key not found")

    api_key.is_active = False
    await db.commit()
    return {"message": f"API key {key_id} revoked"}


# ========== USAGE STATISTICS ==========

@router.get("/stats/users/{user_id}")
async def get_user_stats(user_id: int, db: AsyncSession = Depends(get_db)):
    """Thống kê usage của 1 user"""
    # Kiểm tra user tồn tại
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # Lấy tổng hợp từ usage_logs
    result = await db.execute(
        select(
            UsageLog.service_name,
            UsageLog.status,
            func.count(UsageLog.id).label('count'),
            func.sum(UsageLog.prompt_tokens +
                     UsageLog.completion_tokens).label('total_tokens'),
            func.avg(UsageLog.latency_ms).label('avg_latency')
        )
        .where(UsageLog.user_id == user_id)
        .group_by(UsageLog.service_name, UsageLog.status)
    )
    stats = result.all()

    return {
        "user_id": user_id,
        "username": user.username,
        "stats": [
            {
                "service": s.service_name,
                "status": s.status,
                "count": s.count,
                "total_tokens": s.total_tokens or 0,
                "avg_latency_ms": round(s.avg_latency, 2) if s.avg_latency else 0
            } for s in stats
        ]
    }


@router.get("/stats/top-users")
async def get_top_users(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Top user dùng nhiều token nhất"""
    result = await db.execute(
        select(
            User.id,
            User.username,
            func.count(UsageLog.id).label('request_count'),
            func.sum(UsageLog.prompt_tokens +
                     UsageLog.completion_tokens).label('total_tokens')
        )
        .join(UsageLog, User.id == UsageLog.user_id)
        .group_by(User.id, User.username)
        .order_by(func.sum(UsageLog.prompt_tokens + UsageLog.completion_tokens).desc())
        .limit(limit)
    )
    top_users = result.all()

    return {
        "top_users": [
            {
                "user_id": u.id,
                "username": u.username,
                "request_count": u.request_count,
                "total_tokens": u.total_tokens or 0
            } for u in top_users
        ]
    }
