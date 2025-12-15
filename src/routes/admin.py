from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from src.database import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    CartModel,
    CartItemModel,
    MovieModel,
    get_db,
    # get_current_user,
)
# from src.config.get_current_user import get_current_user

from src.schemas import (
    UserListSchema,
    UserDetailSchema,
    UserGroupUpdateSchema,
    UserActivateSchema,
    CartSchema,
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



@router.get(
    "/cart/{user_id}",
    response_model=CartSchema,
    summary="Get User Cart",
    description="Retrieve the current user's shopping cart. If the cart does not exist, it is automatically created.",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized - User is not logged in."},
        500: {"description": "Internal Server Error - Could not retrieve the cart."},
        404: {"description": "Cart not found."},
    },
)
async def get_user_cart(
    user_id: int,
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db), 
    
) -> CartModel:
    result = await db.execute(
        select(CartModel)
        .options(
        selectinload(CartModel.items)
            .selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres) 
        )
        .where(CartModel.user_id == user_id)
    )
    cart = result.unique().scalar_one_or_none()
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Cart for user with id {user_id} not found."
        )
        
    return cart



@router.get(
    "/carts/",
    response_model=list[CartSchema],
    summary="Get User Cart",
    description="Retrieve all the shopping carts. ",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized - User is not logged in."},
        500: {"description": "Internal Server Error - Could not retrieve the cart."},
        404: {"description": "Cart not found."},
    },
)
async def get_all_carts(
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db), 
    
) -> CartModel:
    result = await db.execute(
        select(CartModel)
        .options(
        selectinload(CartModel.items)
            .selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres) 
        )
    )
    carts = result.scalars().all()
    if not carts:
        return []
        
    return carts


