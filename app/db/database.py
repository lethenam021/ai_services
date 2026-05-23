# app/db/database.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Tạo engine kết nối (có connection pooling)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,                    # Log SQL khi debug
    pool_size=10,                           # Số kết nối tối thiểu
    max_overflow=20,                        # Kết nối thêm khi cao điểm
    pool_pre_ping=True,                     # Kiểm tra kết nối còn sống không
    pool_recycle=3600,                      # Tự động refresh kết nối sau 1h
)

# Tạo session factory (chỉ dùng async_sessionmaker)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Dependency để FastAPI routes có thể dùng session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency - mỗi request có 1 session riêng"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()          # Tự động commit nếu thành công
        except Exception:
            await session.rollback()        # Rollback nếu lỗi
            raise
        finally:
            await session.close()           # Đóng session