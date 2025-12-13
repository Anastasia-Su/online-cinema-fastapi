from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from src.config import get_jwt_auth_manager
from src.config.settings import TestingSettings, Settings, BaseAppSettings
from src.database import get_db
from src.database import UserModel
from src.notifications import EmailSenderInterface, EmailSender
from src.security.interfaces import JWTAuthManagerInterface
from src.security.token_manager import JWTAuthManager
from src.storages import S3StorageInterface, S3StorageClient
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.tasks.redis_blacklist import get_redis, is_token_revoked
from src.exceptions import TokenExpiredError, InvalidTokenError



from src.database import UserModel, UserGroupEnum 
# get_current_user
# from src.config.get_current_user import get_current_user


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    token = credentials.credentials if credentials else None
    print("Token received:", token)
    if not token:
        print("JWT error:",)
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
