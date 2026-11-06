from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    isolation_level="READ COMMITTED",
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


def utcnow() -> datetime:
    """Store UTC as naive DATETIME consistently in MySQL."""
    return datetime.now(UTC).replace(tzinfo=None)


async def get_database() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
