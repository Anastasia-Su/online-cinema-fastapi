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
    PaymentStatusEnum,
    PaymentModel,
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
    description=(
        "Create a new order based on the current user's cart. "
        "All movies in the cart are included in the order, and the total amount is calculated. "
        "Only movies not already purchased are allowed."
    ),
    responses={
        201: {
            "description": "Order placed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "user_id": 1,
                        "status": "pending",
                        "total_amount": 45.50,
                        "items": [
                            {
                                "id": 1,
                                "movie": {"id": 10, "name": "Inception", "price": 20.0},
                                "price_at_order": 20.0,
                            }
                        ],
                    }
                }
            },
        },
        400: {
            "description": "Cart is empty or invalid",
            "content": {"application/json": {"example": {"detail": "Cart is empty."}}},
        },
        409: {
            "description": "Some movies are already in a paid order",
            "content": {
                "application/json": {
                    "example": {"detail": "Movies already in pending order: [10, 12]"}
                }
            },
        },
    },
)
async def place_order(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderResponseSchema:
    """
    Place a new order based on the current user's cart.

    This endpoint creates a new order for all movies in the user's cart,
    calculates the total amount, and stores the order in the database.
    Movies already purchased by the user are rejected.

    :param user: Current authenticated user.
    :type user: UserModel
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: Newly created order with items.
    :rtype: OrderResponseSchema

    :raises HTTPException:
        - 400 if the cart is empty or contains invalid movies.
        - 409 if any movie is already in a paid order.
    """

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
            OrderModel.status == OrderStatusEnum.PAID,
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
        .options(selectinload(OrderModel.items).selectinload(OrderItemModel.movie))
        .where(OrderModel.id == order.id)
    )
    order = result.scalars().first()
    return OrderResponseSchema.model_validate(order)


@router.get(
    "/",
    response_model=list[OrderListResponseSchema],
    summary="Get user orders",
    description="Retrieve all orders for the currently authenticated user, including order items.",
    responses={
        200: {
            "description": "User orders retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": 1,
                            "status": "pending",
                            "total_amount": 45.50,
                            "items": [
                                {
                                    "id": 1,
                                    "movie": {
                                        "id": 10,
                                        "name": "Inception",
                                        "price": 20.0,
                                    },
                                    "price_at_order": 20.0,
                                }
                            ],
                        }
                    ]
                }
            },
        },
        403: {
            "description": "Forbidden – insufficient permissions",
            "content": {
                "application/json": {"example": {"detail": "Not enough permissions"}}
            },
        },
    },
)
async def get_user_orders(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderResponseSchema]:
    """
    Retrieve all orders for the current user.

    Returns a list of orders, each with its associated order items and movie details.

    :param user: Current authenticated user.
    :type user: UserModel
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: List of orders with items.
    :rtype: list[OrderListResponseSchema]

    :raises HTTPException:
        - 403 if the requester lacks sufficient permissions.
    """

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
    description="Cancel a pending order. Only orders with status 'pending' can be canceled.",
    responses={
        200: {
            "description": "Order canceled successfully",
            "content": {
                "application/json": {
                    "example": {"message": "Order canceled successfully."}
                }
            },
        },
        404: {
            "description": "Order not found",
            "content": {
                "application/json": {"example": {"detail": "Order not found."}}
            },
        },
        409: {
            "description": "Order cannot be canceled",
            "content": {
                "application/json": {
                    "example": {"detail": "Only pending orders can be canceled."}
                }
            },
        },
    },
)
async def cancel_order(
    order_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Cancel a pending order.

    Only orders with status 'pending' can be canceled.
    After cancellation, the order status is updated to 'canceled'.

    :param order_id: Unique identifier of the order to cancel.
    :type order_id: int
    :param user: Current authenticated user.
    :type user: UserModel
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: Confirmation message.
    :rtype: dict[str, str]

    :raises HTTPException:
        - 404 if the order does not exist or belongs to another user.
        - 409 if the order is not in pending status.
    """

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


@router.get(
    "/orders/{order_id}/payment-status",
    summary="Get payment status for an order",
    description="Retrieve the latest payment status for a given order.",
    responses={
        200: {
            "description": "Payment status retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "processing": {
                            "summary": "Processing",
                            "value": {
                                "status": "processing",
                                "message": "Payment is being processed",
                            },
                        },
                        "success": {
                            "summary": "Success",
                            "value": {
                                "status": "success",
                                "message": "Payment successful",
                            },
                        },
                        "refunded": {
                            "summary": "Refunded",
                            "value": {
                                "status": "refunded",
                                "message": "Payment refunded",
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "Order not found",
            "content": {"application/json": {"example": {"detail": "Order not found"}}},
        },
    },
)
async def get_payment_status(
    order_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Retrieve the payment status for a specific order.

    Returns the latest payment status: processing, success, or refunded.

    :param order_id: Unique identifier of the order.
    :type order_id: int
    :param current_user: Current authenticated user.
    :type current_user: UserModel
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: Payment status with message.
    :rtype: dict[str, str]

    :raises HTTPException:
        - 404 if the order does not exist or belongs to another user.
    """

    order = await db.execute(
        select(OrderModel).where(
            OrderModel.id == order_id,
            OrderModel.user_id == current_user.id,
        )
    )
    order = order.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = await db.execute(
        select(PaymentModel)
        .where(PaymentModel.order_id == order_id)
        .order_by(PaymentModel.created_at.desc())
        .limit(1)
    )
    payment = payment.scalar_one_or_none()

    if not payment:
        return {
            "status": "processing",
            "message": "Payment is being processed",
        }

    if payment.status == PaymentStatusEnum.SUCCESSFUL:
        return {
            "status": "success",
            "message": "Payment successful",
        }

    if payment.status == PaymentStatusEnum.REFUNDED:
        return {
            "status": "refunded",
            "message": "Payment refunded",
        }
