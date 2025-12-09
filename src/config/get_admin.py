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
from src.config.get_current_user import get_current_user


bearer_scheme = HTTPBearer(auto_error=False)


def require_admin(user: UserModel = Depends(get_current_user)):
    if not user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


async def require_moderator_or_admin(
    user: UserModel = Depends(get_current_user),
):

    if not (
        user.has_group(UserGroupEnum.MODERATOR) or user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator or Admin access required",
        )
    return user


