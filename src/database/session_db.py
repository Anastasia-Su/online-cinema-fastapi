from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.config.get_settings import get_settings

from fastapi.security import HTTPBearer


bearer_scheme = HTTPBearer(auto_error=False)


settings = get_settings()


DATABASE_URL_ASYNC = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
    f"{settings.POSTGRES_HOST}:{settings.POSTGRES_DB_PORT}/{settings.POSTGRES_DB}"
)

DATABASE_URL_SYNC = DATABASE_URL_ASYNC.replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
)


async_engine = create_async_engine(DATABASE_URL_ASYNC, echo=False)

AsyncSessionLocal = sessionmaker(
    async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# Sync engine for Alembic migrations

sync_engine = create_engine(DATABASE_URL_SYNC, echo=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_db_contextmanager() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
