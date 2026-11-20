"""SQLAlchemy async engine, session factory, and declarative base."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

import ssl as _ssl

settings = get_settings()

# asyncpg doesn't support sslmode/ssl as URL params for Neon.
# Strip it from the URL and pass ssl context via connect_args instead.
from sqlalchemy.engine import make_url
parsed_url = make_url(settings.DATABASE_URL)
query = dict(parsed_url.query)
ssl_mode = query.pop("sslmode", query.pop("ssl", None))
query.pop("channel_binding", None)
db_url = parsed_url.set(query=query)
connect_args: dict = {}
if ssl_mode in {"require", "verify-full", "verify-ca"} or "neon.tech" in (parsed_url.host or ""):
    connect_args["ssl"] = _ssl.create_default_context()

engine = create_async_engine(
    db_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
