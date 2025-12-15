from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import select, delete, exists
from src.database import (
    get_db,
    CartModel,
    CartItemModel,
    UserModel,
    MovieModel,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
)
from src.config.get_current_user import get_current_user
from src.schemas import (
    CartSchema,
    CartItemSchema,
    MovieCartSchema,
    OrderResponseSchema,
    OrderListResponseSchema,
    OrderItemResponseSchema,
    MovieListItemSchema,
)


router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "/",
    response_model=OrderResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Place order from cart",
)
async def place_order(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CartModel)
        .options(
            selectinload(CartModel.items)
            .selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres)
        )
        .where(CartModel.user_id == user.id)
    )
    cart = result.unique().scalar_one_or_none()
    if not cart or not cart.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty.",
        )

    movie_ids = [item.movie_id for item in cart.items]

    # Fetch all movies from the DB to ensure they exist and are loaded
    movies_result = await db.execute(
        select(MovieModel).where(MovieModel.id.in_(movie_ids))
    )
    movies = movies_result.scalars().all()
    movies_by_id = {movie.id: movie for movie in movies}

    if not movies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid movies in the cart.",
        )

    # Check for any movies already in pending orders
    existing_order_stmt = (
        select(OrderItemModel.movie_id)
        .join(OrderModel, OrderItemModel.order_id == OrderModel.id)
        .where(
            OrderModel.user_id == user.id,
            OrderModel.status == OrderStatusEnum.PENDING,
            OrderItemModel.movie_id.in_(movie_ids),
        )
    )
    existing_result = await db.execute(existing_order_stmt)
    existing_movie_ids = {row[0] for row in existing_result.fetchall()}

    if existing_movie_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Movies already in pending order: {list(existing_movie_ids)}",
        )

    
    total_amount = sum(Decimal(str(movies_by_id[mid].price)) for mid in movie_ids)
    
    order = OrderModel(
        user_id=user.id,
        status=OrderStatusEnum.PENDING,
        total_amount=total_amount,
    )

    order.items = [
        OrderItemModel(
            movie_id=movie.id,
            price_at_order=movie.price,
        )
        for movie in movies
    ]

    db.add(order)
    await db.commit()
    await db.refresh(order)
    result = await db.execute(
        select(OrderModel)
        .options(
            selectinload(OrderModel.items)
            .selectinload(OrderItemModel.movie)
        )
        .where(OrderModel.id == order.id)
    )
    order = result.scalars().first()
    return OrderResponseSchema.model_validate(order)


@router.get(
    "/",
    response_model=list[OrderListResponseSchema],
    summary="Get user orders",
)
async def get_user_orders(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderModel)
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.movie))
        .where(OrderModel.user_id == user.id)
        .order_by(OrderModel.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/{order_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel pending order",
)
async def cancel_order(
    order_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await db.get(OrderModel, order_id)

    if not order or order.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found."
        )

    if order.status != OrderStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending orders can be canceled.",
        )

    order.status = OrderStatusEnum.CANCELED
    await db.commit()

    return {"message": "Order canceled successfully."}
