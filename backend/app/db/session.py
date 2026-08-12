"""SQLAlchemy async engine, session factory, and declarative base."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

import ssl as _ssl

settings = get_settings()

# asyncpg doesn't support sslmode/ssl as URL params for Neon.
# Strip it from the URL and pass ssl context via connect_args instead.
db_url = settings.DATABASE_URL
connect_args: dict = {}

if "neon.tech" in db_url or "ssl=require" in db_url or "sslmode=require" in db_url:
    # Remove ssl/sslmode params from URL
    for param in ["?ssl=require", "&ssl=require", "?sslmode=require", "&sslmode=require",
                  "?channel_binding=require", "&channel_binding=require"]:
        db_url = db_url.replace(param, "")
    # Clean up leftover ? or &
    if db_url.endswith("?") or db_url.endswith("&"):
        db_url = db_url[:-1]
    # Use SSL context for asyncpg
    ssl_context = _ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = _ssl.CERT_NONE
    connect_args["ssl"] = ssl_context

engine = create_async_engine(
    db_url,
    echo=settings.APP_ENV == "development",
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
