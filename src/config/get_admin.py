from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from src.database import UserModel, UserGroupEnum
from src.config.get_current_user import get_current_user


bearer_scheme = HTTPBearer(auto_error=False)


def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    """Allow access only to users with ADMIN privileges."""

    if not user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


async def require_moderator_or_admin(
    user: UserModel = Depends(get_current_user),
) -> UserModel:
    """Allow access to users with MODERATOR or ADMIN privileges."""

    if not (
        user.has_group(UserGroupEnum.MODERATOR) or user.has_group(UserGroupEnum.ADMIN)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator or Admin access required",
        )
    return user
