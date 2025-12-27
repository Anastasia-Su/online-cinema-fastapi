from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from aioredis import Redis
from src.config import get_jwt_auth_manager
from src.database import get_db, UserModel
from src.security.interfaces import JWTAuthManagerInterface
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.tasks.redis_blacklist import get_redis, is_token_revoked
from src.exceptions import TokenExpiredError, InvalidTokenError


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    """Authenticate the request and return the current user from a JWT token."""

    token = credentials.credentials if credentials else None
    print("Token received:", token)
    if not token:
        print(
            "JWT error:",
        )
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
    print("Decoded user_id:", user_id)

    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group))
        .where(UserModel.id == user_id)
    )
    user = result.scalars().first()
    return user
