"""SQLAlchemy async engine, session factory, and database bootstrap."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from configs.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level.upper() == "DEBUG",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, closing it when the caller is done."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables defined by the ORM metadata.

    Safe to call repeatedly -- SQLAlchemy's ``create_all`` is a no-op for
    tables that already exist.
    """
    from src.db.models import Base  # noqa: E402 -- deferred to avoid circular imports

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
