import stripe
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Request, Path
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
    PaymentItemModel
)
from src.config import BaseAppSettings
from src.config.get_current_user import get_current_user
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

from .utils import delete_paid_items_for_user

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    order_id: int,
    user: UserModel = Depends(get_current_user),
    settings: BaseAppSettings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    order = await db.execute(
        select(OrderModel)
        .options(selectinload(OrderModel.items))
        .where(
            OrderModel.id == order_id,
            OrderModel.user_id == user.id,
            OrderModel.status == OrderStatusEnum.PENDING,
        )
    )
    order = order.scalar_one_or_none()

    if not order:
        raise HTTPException(404, "Order not found or not payable")

    # Validate total
    calculated_total = sum(
        Decimal(str(item.price_at_order)) for item in order.items
    )

    if calculated_total != order.total_amount:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order total mismatch")

    # Create Stripe PaymentIntent
    intent = stripe.PaymentIntent.create(
        amount=int(order.total_amount * 100),  # cents
        currency="usd",
        payment_method_types=["card"],
        metadata={
            "order_id": order.id,
            "user_id": user.id,
        },
    )

    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
    }
    
    
@router.post("/{payment_id}/cancel")
async def cancel_payment(payment_id: int, _: UserModel = Depends(get_current_user), settings: BaseAppSettings = Depends(get_settings), db: AsyncSession = Depends(get_db)):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    payment = await db.get(PaymentModel, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")

    if payment.status in [PaymentStatusEnum.SUCCESSFUL, PaymentStatusEnum.REFUNDED]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Only pending payments can be canceled.",
        )
    if payment.external_payment_id:
        stripe.PaymentIntent.cancel(payment.external_payment_id)

    payment.status = PaymentStatusEnum.CANCELED
    await db.commit()
    return {"message": "Payment canceled successfully"}

    
@router.post("/webhook")
async def stripe_webhook(
    request: Request, 
    settings: BaseAppSettings = Depends(get_settings),
    # _: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]

        order_id = int(intent["metadata"]["order_id"])
        user_id = int(intent["metadata"]["user_id"])

        order = await db.execute(
            select(OrderModel)
            .options(selectinload(OrderModel.items))
            .where(OrderModel.id == order_id)
        )
        order = order.scalar_one()

        # Idempotency check
        existing = await db.execute(
            select(PaymentModel)
            .where(PaymentModel.external_payment_id == intent.id)
        )
        if existing.scalar_one_or_none():
            return {"status": "already_processed"}

        payment = PaymentModel(
            user_id=user_id,
            order_id=order.id,
            amount=order.total_amount,
            status=PaymentStatusEnum.SUCCESSFUL,
            external_payment_id=intent.id,
        )

        payment.items = [
            PaymentItemModel(
                order_item_id=item.id,
                price_at_payment=item.price_at_order,
            )
            for item in order.items
        ]

        order.status = OrderStatusEnum.PAID

        db.add(payment)
        
        await delete_paid_items_for_user(
            db=db,
            user_id=user_id,
        )

        await db.commit()  

    elif event["type"] == "payment_intent.payment_failed":
        # optional logging
        pass

    return {"status": "ok"}


@router.get(
    "/",
    response_model=list[PaymentListSchema],
)
async def get_user_payments(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentModel)
        .where(PaymentModel.user_id == user.id)
        .order_by(PaymentModel.created_at.desc())
    )
    return result.scalars().all()



@router.get(
    "/{payment_id}",
    response_model=PaymentResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get payment details",
)
async def get_payment_detail(
    payment_id: int,
    _: UserModel = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentModel)
        .options(selectinload(PaymentModel.items))
        .where(PaymentModel.id == payment_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payment not found")

  
    return PaymentResponseSchema.model_validate(payment)


# @router.delete(
#     "/delete-paid",
#     summary="Delete paid items from Cart",
#     status_code=status.HTTP_204_NO_CONTENT,
# )
# async def delete_paid_items_from_cart(
#     db: AsyncSession = Depends(get_db),
#     user: UserModel = Depends(get_current_user),
# ) -> None:
#     # 1. Get user's cart
#     cart_result = await db.execute(
#         select(CartModel).where(CartModel.user_id == user.id)
#     )
#     cart = cart_result.scalar_one_or_none()

#     if not cart:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Cart not found",
#         )

#     # 2. Get all SUCCESSFUL payments for this user
#     payment_items_subquery = (
#         select(OrderItemModel.movie_id)
#         .join(PaymentItemModel, PaymentItemModel.order_item_id == OrderItemModel.id)
#         .join(PaymentModel, PaymentModel.id == PaymentItemModel.payment_id)
#         .where(
#             PaymentModel.status == PaymentStatusEnum.SUCCESSFUL,
#             PaymentModel.user_id == user.id,
#         )
#     )

#     # 3. Delete ONLY cart items that were paid
#     result = await db.execute(
#         delete(CartItemModel)
#         .where(
#             CartItemModel.cart_id == cart.id,
#             CartItemModel.movie_id.in_(payment_items_subquery),
#         )
#     )

#     if result.rowcount == 0:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="No paid items found in cart",
#         )

#     await db.commit()

