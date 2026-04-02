from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_async_engine_and_session(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        future=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory

