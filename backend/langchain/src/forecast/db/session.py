from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from forecast.config import get_settings


@lru_cache
def get_engine(database_url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        database_url or settings.sqlalchemy_database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )


@lru_cache
def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(database_url),
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
