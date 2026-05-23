# init_db.py
import asyncio
from app.db.database import engine
from app.db.base import Base

# Import models để Base biết mà tạo bảng
from app.db.entity.user import User
from app.db.entity.api_key import APIKey


async def init():
    print("Đang tạo bảng...")
    async with engine.begin() as conn:
        # Tạo tất cả bảng chưa có
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Đã tạo bảng thành công!")

if __name__ == "__main__":
    asyncio.run(init())
