from fastapi import Depends, HTTPException, status

from src.database import UserModel, UserGroupEnum, get_current_user


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
