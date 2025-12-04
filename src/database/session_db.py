from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, joinedload

from src.config import get_jwt_auth_manager
from src.config.get_settings import get_settings

import os

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import TestingSettings, Settings, BaseAppSettings
from src.database import UserModel
from src.notifications import EmailSenderInterface, EmailSender
from src.security.interfaces import JWTAuthManagerInterface
from src.security.token_manager import JWTAuthManager
from src.storages import S3StorageInterface, S3StorageClient
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.tasks.redis_blacklist import get_redis, is_token_revoked
from src.exceptions import TokenExpiredError, InvalidTokenError


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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token"
        )

    if await is_token_revoked(token, redis):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked"
        )

    try:
        payload = jwt_manager.decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token validation failed"
        ) from e
    print("payload", payload)

    user_id = payload.get("user_id")

    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group))
        .where(UserModel.id == user_id)
    )
    user = result.scalars().first()
    return user
