from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from src.database import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    get_db,
    # get_current_user,
)
# from src.config.get_current_user import get_current_user

from src.schemas import (
    UserListSchema,
    UserDetailSchema,
    UserGroupUpdateSchema,
    UserActivateSchema,
)
from src.config.get_admin import require_admin
from .utils import backfill_all_counters

router = APIRouter(prefix="/admin", tags=["admin"])


@router.patch("/users/{user_id}/group", response_model=dict)
async def change_user_group(
    user_id: int,
    data: UserGroupUpdateSchema,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_admin),
):

    result = await db.execute(
        select(UserGroupModel).where(UserGroupModel.name == data.group)
    )
    group = result.scalars().first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid group: {data.group}"
        )

    await db.execute(
        update(UserModel).where(UserModel.id == user_id).values(group_id=group.id)
    )
    await db.commit()
    return {"detail": f"User {user_id} is now {data.group}"}


@router.patch("/users/{user_id}/activate", response_model=dict)
async def activate_user(
    user_id: int,
    data: UserActivateSchema,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_admin),
):
    result = await db.execute(
        update(UserModel)
        .where(UserModel.id == user_id)
        .values(is_active=data.is_active)
        .returning(UserModel.id)
    )
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    await db.commit()
    status_text = "activated" if data.is_active else "deactivated"
    return {"detail": f"User {user_id} has been {status_text}"}


@router.post("/recount-all-counters")
async def recount_all_counters(
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db),  # ← direct injection, perfect
):
    await backfill_all_counters(db=db)
    return {"message": "Recount started"}
