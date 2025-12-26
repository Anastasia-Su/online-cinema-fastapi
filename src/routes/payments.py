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
    PaymentItemModel,
)
from src.config import BaseAppSettings, get_accounts_email_notificator
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
from src.notifications import EmailSenderInterface

from .utils import delete_paid_items_for_user

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/create",
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment for an order",
    description=(
        "Creates a Stripe PaymentIntent for a pending order. "
        "Validates the order total and returns the `client_secret` "
        "for the frontend to complete the payment."
    ),
    responses={
        201: {
            "description": "PaymentIntent created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "client_secret": "pi_3Kxyz_secret_ABC123",
                        "payment_intent_id": "pi_3Kxyz",
                    }
                }
            },
        },
        400: {
            "description": "Invalid request (total mismatch)",
            "content": {
                "application/json": {"example": {"detail": "Order total mismatch"}}
            },
        },
        404: {
            "description": "Order not found or not payable",
            "content": {
                "application/json": {
                    "example": {"detail": "Order not found or not payable"}
                }
            },
        },
    },
)
async def create_payment(
    order_id: int,
    user: UserModel = Depends(get_current_user),
    settings: BaseAppSettings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Create a Stripe PaymentIntent for a pending order.

    Validates the order exists and the total matches the sum of the items' prices.
    Returns a client secret for frontend Stripe integration.

    :param order_id: ID of the order to pay.
    :type order_id: int
    :param user: Current authenticated user.
    :type user: UserModel
    :param settings: Application settings with Stripe credentials.
    :type settings: BaseAppSettings
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession

    :return: Client secret and PaymentIntent ID.
    :rtype: dict[str, str]

    :raises HTTPException:
        - 400 if the order total does not match the sum of items.
        - 404 if the order does not exist or is not pending.
    """

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
    calculated_total = sum(Decimal(str(item.price_at_order)) for item in order.items)

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


@router.post(
    "/webhook",
    summary="Stripe payment webhook",
    description=(
        "Handles Stripe webhook events such as `payment_intent.succeeded` and `payment_intent.payment_failed`. "
        "Updates order and payment records and sends email notifications to the user."
    ),
    responses={
        200: {
            "description": "Webhook processed successfully",
            "content": {"application/json": {"example": {"status": "ok"}}},
        },
        400: {
            "description": "Invalid Stripe signature",
            "content": {
                "application/json": {"example": {"detail": "Invalid signature"}}
            },
        },
    },
)
async def stripe_webhook(
    request: Request,
    settings: BaseAppSettings = Depends(get_settings),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Handle Stripe webhook events.

    Processes `payment_intent.succeeded` and `payment_intent.payment_failed` events.
    Updates the order status and creates payment records if successful.
    Sends email notifications to the user.

    :param request: Incoming webhook request from Stripe.
    :type request: Request
    :param settings: Application settings with Stripe credentials.
    :type settings: BaseAppSettings
    :param email_sender: Service for sending email notifications.
    :type email_sender: EmailSenderInterface
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession

    :return: Status of webhook processing.
    :rtype: dict[str, str]

    :raises HTTPException:
        - 400 if the Stripe signature is invalid.
    """

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
            select(PaymentModel).where(PaymentModel.external_payment_id == intent["id"])
        )
        if existing.scalar_one_or_none():
            return {"status": "already_processed"}

        payment = PaymentModel(
            user_id=user_id,
            order_id=order.id,
            amount=order.total_amount,
            status=PaymentStatusEnum.SUCCESSFUL,
            external_payment_id=intent["id"],
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
        await db.flush()

        await delete_paid_items_for_user(
            db=db,
            user_id=user_id,
        )

        await db.commit()

        header = "Payment succeeded"
        message = f"Your payment for the order {order_id} is successful.<br />Payment id: {intent['id']}<br />Amount: {intent['amount'] / 100}"
        user = await db.get(UserModel, user_id)

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        order_id = int(intent["metadata"]["order_id"])
        user_id = int(intent["metadata"]["user_id"])
        amount = intent["amount"] / 100

        header = "Payment failed"
        message = f"Your payment of ${amount} for order {order_id} failed.<br />Reason: {intent['last_payment_error']['message']}"

        user = await db.get(UserModel, user_id)

    else:
        return {"status": "ignored"}

    await email_sender.send_payment_email(user.email, header, message)
    return {"status": "ok"}


@router.get(
    "/",
    response_model=list[PaymentListSchema],
    summary="Get all user payments",
    description="Retrieve all payment records for the current user, ordered by creation date descending.",
    responses={
        200: {
            "description": "List of user payments",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": 1,
                            "order_id": 10,
                            "amount": 45.50,
                            "status": "successful",
                            "created_at": "2025-12-26T12:00:00Z",
                        }
                    ]
                }
            },
        }
    },
)
async def get_user_payments(
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentListSchema]:
    """
    Retrieve all payments for the current user.

    :param user: Current authenticated user.
    :type user: UserModel
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession

    :return: List of payment records.
    :rtype: list[PaymentListSchema]
    """

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
    description="Retrieve details for a specific payment by ID, including associated order items.",
    responses={
        200: {
            "description": "Payment retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "order_id": 10,
                        "user_id": 1,
                        "amount": 45.50,
                        "status": "successful",
                        "items": [
                            {
                                "id": 1,
                                "order_item_id": 5,
                                "price_at_payment": 20.0,
                                "movie": {"id": 10, "name": "Inception", "price": 20.0},
                            }
                        ],
                    }
                }
            },
        },
        404: {
            "description": "Payment not found",
            "content": {
                "application/json": {"example": {"detail": "Payment not found"}}
            },
        },
    },
)
async def get_payment_detail(
    payment_id: int,
    _: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponseSchema:
    """
    Retrieve payment details by payment ID.

    :param payment_id: Unique identifier of the payment.
    :type payment_id: int
    :param _: Current authenticated user.
    :type _: UserModel
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession

    :return: Payment details including order items.
    :rtype: PaymentResponseSchema

    :raises HTTPException:
        - 404 if the payment does not exist.
    """

    result = await db.execute(
        select(PaymentModel)
        .options(selectinload(PaymentModel.items))
        .where(PaymentModel.id == payment_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return PaymentResponseSchema.model_validate(payment)
