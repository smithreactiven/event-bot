"""Скрипт для очистки базы данных."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+asyncpg://gen_user:3u79JGd2p9yjQ2h4@5.129.203.85:5432/default_db"


async def main():
    engine = create_async_engine(DB_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Очищаем в правильном порядке (из-за foreign keys)
        await session.execute(text("DELETE FROM opinion"))
        await session.execute(text("DELETE FROM round_message"))
        await session.execute(text("DELETE FROM round"))
        await session.execute(text("DELETE FROM participant"))
        await session.execute(text("DELETE FROM event"))
        await session.commit()
        print("База данных очищена!")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
