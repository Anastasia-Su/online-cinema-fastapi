from datetime import datetime
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
    OrderModel,
    OrderItemModel,
    OrderStatusEnum,
    get_db,
)


from src.schemas import (
    UserListSchema,
    UserDetailSchema,
    UserGroupUpdateSchema,
    UserActivateSchema,
    CartSchema,
    OrderResponseSchema,
)
from src.config.get_admin import require_admin
from .utils import backfill_all_counters
import stripe
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import select, delete, exists
from src.config.get_settings import get_settings
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
    PaymentItemModel,
)
from src.config import BaseAppSettings
from src.schemas import (
    CartSchema,
    CartItemSchema,
    MovieCartSchema,
    OrderResponseSchema,
    OrderListResponseSchema,
    OrderItemResponseSchema,
    MovieListItemSchema,
    PaymentItemResponseSchema,
    PaymentListSchema,
    PaymentResponseSchema,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.patch(
    "/users/{user_id}/group",
    response_model=dict,
    summary="Change a user's group",
    description="Update the permission group assigned to a user. Admin-only endpoint.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "User group updated successfully"},
        404: {
            "description": "Invalid group",
            "content": {
                "application/json": {"example": {"detail": "Invalid group: MODERATOR"}}
            },
        },
        401: {"description": "Unauthorized - Admin privileges required"},
    },
)
async def change_user_group(
    user_id: int,
    data: UserGroupUpdateSchema,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    """
    Change a user's permission group.

    Updates the group assigned to a specific user. This endpoint is restricted
    to administrators only.

    Args:
        user_id (int): ID of the user whose group will be updated.
        data (UserGroupUpdateSchema): Target user group.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Confirmation message indicating the new group.

    Raises:
        HTTPException:
            - 404 Not Found if the provided group does not exist.
    """

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


@router.patch(
    "/users/{user_id}/activate",
    response_model=dict,
    summary="Activate or deactivate a user",
    description="Enable or disable a user account. Admin-only endpoint.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "User activation status updated successfully"},
        404: {
            "description": "User not found",
            "content": {"application/json": {"detail": "User not found"}},
        },
        401: {"description": "Unauthorized - Admin privileges required"},
    },
)
async def activate_user(
    user_id: int,
    data: UserActivateSchema,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    """
    Activate or deactivate a user account.

    Allows an administrator to enable or disable a user's account
    by updating the `is_active` flag.

    Args:
        user_id (int): ID of the user to update.
        data (UserActivateSchema): Activation state payload.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Confirmation message indicating activation status.

    Raises:
        HTTPException:
            - 404 Not Found if the user does not exist.
    """
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


@router.post(
    "/recount-all-counters",
    status_code=status.HTTP_200_OK,
    summary="Recount all cached counters",
    description="Triggers recalculation of all denormalized counters (likes, ratings, etc.). Admin-only.",
    responses={
        200: {"description": "Recount started successfully"},
        401: {"description": "Unauthorized - Admin privileges required"},
        500: {"description": "Internal Server Error - Recount failed"},
    },
)
async def recount_all_counters(
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db),  # ← direct injection, perfect
) -> dict:
    """
    Recalculate and backfill all cached counters.

    Triggers a background recalculation of denormalized counters
    (e.g. likes, favorites, ratings). Intended for administrative
    maintenance and data consistency.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Status message indicating the recount has started.
    """

    await backfill_all_counters(db=db)
    return {"message": "Recount started"}


@router.get(
    "/cart/{user_id}",
    response_model=CartSchema,
    summary="Get User Cart",
    description="Retrieve the current user's shopping cart. If the cart does not exist, it is automatically created.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Cart retrieved successfully"},
        401: {"description": "Unauthorized - User is not logged in."},
        404: {
            "description": "Cart not found",
            "content": {
                "application/json": {"detail": "Cart for user with id 1 not found."}
            },
        },
        500: {"description": "Internal Server Error - Could not retrieve the cart."},
    },
)
async def get_user_cart(
    user_id: int,
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CartModel:
    """
    Retrieve a specific user's shopping cart.

    Loads the user's cart along with cart items, associated movies,
    and movie genres. This endpoint is restricted to administrators.

    Args:
        user_id (int): ID of the user whose cart is requested.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CartModel: The user's cart with items and movie details.

    Raises:
        HTTPException:
            - 404 Not Found if the cart does not exist.
    """

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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart for user with id {user_id} not found.",
        )

    return cart


@router.get(
    "/carts/",
    response_model=list[CartSchema],
    summary="Get User Cart",
    description="Retrieve all the shopping carts. ",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "All carts retrieved successfully"},
        401: {"description": "Unauthorized - User is not logged in."},
        500: {"description": "Internal Server Error - Could not retrieve the cart."},
        404: {"description": "Cart not found."},
    },
)
async def get_all_carts(
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[CartModel]:
    """
    Retrieve all user shopping carts.

    Returns a list of all carts in the system, including their items
    and related movie information. Accessible to administrators only.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        list[CartModel]: List of carts. Returns an empty list if none exist.
    """

    result = await db.execute(
        select(CartModel).options(
            selectinload(CartModel.items)
            .selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres)
        )
    )
    carts = result.scalars().all()
    if not carts:
        return []

    return carts


@router.get(
    "/orders",
    response_model=list[OrderResponseSchema],
    summary="List all orders",
    description="Retrieve all orders with optional filtering by user, status, and date range. Admin-only endpoint.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Orders retrieved successfully"},
        401: {"description": "Unauthorized - Admin privileges required"},
        500: {"description": "Internal Server Error - Failed to retrieve orders"},
    },
)
async def admin_list_orders(
    user_id: int | None = None,
    status: OrderStatusEnum | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[OrderModel]:
    """
    Retrieve a list of all orders with optional filters.

    Allows administrators to filter orders by user, status,
    and creation date range.

    Args:
        user_id (int | None): Filter orders by user ID.
        status (OrderStatusEnum | None): Filter by order status.
        date_from (datetime | None): Include orders created after this date.
        date_to (datetime | None): Include orders created before this date.
        db (AsyncSession): Asynchronous database session.

    Returns:
        list[OrderModel]: List of matching orders with items and movies.
    """

    stmt = select(OrderModel).options(
        selectinload(OrderModel.items).selectinload(OrderItemModel.movie)
    )

    if user_id:
        stmt = stmt.where(OrderModel.user_id == user_id)
    if status:
        stmt = stmt.where(OrderModel.status == status)
    if date_from:
        stmt = stmt.where(OrderModel.created_at >= date_from)
    if date_to:
        stmt = stmt.where(OrderModel.created_at <= date_to)

    result = await db.execute(stmt.order_by(OrderModel.created_at.desc()))
    return result.scalars().all()


@router.get(
    "/payments",
    response_model=list[PaymentListSchema],
    summary="List all payments",
    description="Retrieve all payments with optional filtering by user, status, and date range. Admin-only endpoint.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Payments retrieved successfully"},
        401: {"description": "Unauthorized - Admin privileges required"},
        500: {"description": "Internal Server Error - Failed to retrieve payments"},
    },
)
async def admin_list_payments(
    user_id: int | None = None,
    status: PaymentStatusEnum | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _: UserModel = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentModel]:
    """
    Retrieve a list of all payments with optional filters.

    Allows administrators to view and filter payment records
    by user, status, and creation date range.

    Args:
        user_id (int | None): Filter payments by user ID.
        status (PaymentStatusEnum | None): Filter by payment status.
        date_from (datetime | None): Include payments created after this date.
        date_to (datetime | None): Include payments created before this date.
        db (AsyncSession): Asynchronous database session.

    Returns:
        list[PaymentModel]: List of matching payment records.
    """

    stmt = select(PaymentModel)

    if user_id:
        stmt = stmt.where(PaymentModel.user_id == user_id)
    if status:
        stmt = stmt.where(PaymentModel.status == status)
    if date_from:
        stmt = stmt.where(PaymentModel.created_at >= date_from)
    if date_to:
        stmt = stmt.where(PaymentModel.created_at <= date_to)

    result = await db.execute(stmt.order_by(PaymentModel.created_at.desc()))
    return result.scalars().all()


@router.post(
    "/payments/{payment_id}/refund",
    status_code=status.HTTP_200_OK,
    summary="Refund a payment",
    description="Refund a successful payment via Stripe and update order and payment statuses. Admin-only endpoint.",
    responses={
        200: {"description": "Payment refunded successfully"},
        404: {
            "description": "Payment not found",
            "content": {"application/json": {"detail": "Payment not found"}},
        },
        409: {
            "description": "Payment cannot be refunded",
            "content": {"application/json": {"detail": "Payment is already refunded"}},
        },
        400: {
            "description": "Stripe error",
            "content": {"application/json": {"detail": "Stripe error: ..."}},
        },
        401: {"description": "Unauthorized - Admin privileges required"},
    },
)
async def refund_payment(
    payment_id: int,
    settings: BaseAppSettings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict:
    """
    Refund a successful payment via Stripe.

    Issues a refund through Stripe for the specified payment and updates
    both the payment and associated order statuses to `REFUNDED`.

    Only payments with status `SUCCESSFUL` can be refunded.
    This operation is restricted to administrators.

    Args:
        payment_id (int): ID of the payment to refund.
        settings (BaseAppSettings): Application settings containing Stripe credentials.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Refund details including payment ID, new status, and Stripe refund ID.

    Raises:
        HTTPException:
            - 404 Not Found if the payment does not exist.
            - 409 Conflict if the payment is already refunded or not eligible.
            - 400 Bad Request if Stripe refund fails.
    """

    stripe.api_key = settings.STRIPE_SECRET_KEY

    result = await db.execute(select(PaymentModel).where(PaymentModel.id == payment_id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if payment.status == PaymentStatusEnum.REFUNDED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Payment is already refunded"
        )

    if payment.status not in [PaymentStatusEnum.SUCCESSFUL, PaymentStatusEnum.REFUNDED]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Only successful payments can be refunded",
        )

    try:
        stripe_refund = stripe.Refund.create(payment_intent=payment.external_payment_id)
    except stripe.error.StripeError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}"
        )

    payment.status = PaymentStatusEnum.REFUNDED

    db.add(payment)
    await db.flush()

    order = await db.execute(
        select(OrderModel)
        .options(selectinload(OrderModel.items))
        .where(OrderModel.id == payment.order_id)
    )

    order = order.scalar_one()
    order.status = OrderStatusEnum.REFUNDED

    db.add(order)
    await db.commit()

    return {
        "payment_id": payment.id,
        "status": payment.status.value,
        "stripe_refund_id": stripe_refund.id,
    }
