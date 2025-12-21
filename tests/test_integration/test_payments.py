import pytest
import json
from decimal import Decimal
from sqlalchemy import select
from unittest.mock import patch


from src.database import OrderModel, OrderStatusEnum, PaymentModel, PaymentStatusEnum
from ..utils import get_headers


@pytest.mark.asyncio
async def test_create_payment_success(client, db_session, jwt_manager):
    """
    Successfully create Stripe PaymentIntent for a pending order.
    """

    result = await db_session.execute(
        select(OrderModel).where(OrderModel.status == OrderStatusEnum.PENDING)
    )
    order = result.scalars().first()
    assert order is not None

    headers = await get_headers(db_session, jwt_manager)

    fake_intent = type(
        "Intent",
        (),
        {
            "id": "pi_test_123",
            "client_secret": "secret_123",
        },
    )()

    with patch("stripe.PaymentIntent.create", return_value=fake_intent):
        response = await client.post(
            "/payments/create",
            params={"order_id": order.id},
            headers=headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["payment_intent_id"] == "pi_test_123"
    assert data["client_secret"] == "secret_123"


@pytest.mark.asyncio
async def test_create_payment_order_not_found(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager, 1)

    response = await client.post(
        "/payments/create",
        params={"order_id": 999999},
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_payment_total_mismatch(client, db_session, jwt_manager):
    """
    Tamper order total to trigger validation error.
    """
    result = await db_session.execute(
        select(OrderModel).where(OrderModel.status == OrderStatusEnum.PENDING)
    )
    order = result.scalars().first()
    assert order is not None

    order.total_amount = Decimal("9999.99")
    await db_session.commit()

    headers = await get_headers(db_session, jwt_manager)

    response = await client.post(
        "/payments/create",
        params={"order_id": order.id},
        headers=headers,
    )

    assert response.status_code == 400
    assert "total mismatch" in response.text.lower()


@pytest.mark.asyncio
async def test_webhook_payment_succeeded(client, db_session, email_sender_stub):
    order = (
        (
            await db_session.execute(
                select(OrderModel).where(OrderModel.status == OrderStatusEnum.PENDING)
            )
        )
        .scalars()
        .first()
    )

    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_123",
                "amount": 5000,
                "metadata": {
                    "order_id": str(order.id),
                    "user_id": str(order.user_id),
                },
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=payload):
        response = await client.post(
            "/payments/webhook",
            content=json.dumps(payload),
            headers={"stripe-signature": "test"},
        )

    assert response.status_code == 200

    payment = (
        await db_session.execute(
            select(PaymentModel).where(
                PaymentModel.external_payment_id == "pi_test_123"
            )
        )
    ).scalar_one()

    assert payment.status == PaymentStatusEnum.SUCCESSFUL

    await db_session.refresh(order)
    assert order.status == OrderStatusEnum.PAID


@pytest.mark.asyncio
async def test_webhook_idempotent(client, db_session):
    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_duplicate",
                "amount": 5000,
                "metadata": {"order_id": "1", "user_id": "1"},
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=payload):
        r1 = await client.post(
            "/payments/webhook",
            content=json.dumps(payload),
            headers={"stripe-signature": "test"},
        )
        r2 = await client.post(
            "/payments/webhook",
            content=json.dumps(payload),
            headers={"stripe-signature": "test"},
        )

    assert r2.json()["status"] == "already_processed"


@pytest.mark.asyncio
async def test_get_user_payments(client, db_session, jwt_manager):
    """
    GET /payments/ should return list of payments for current user
    """

    order = (
        (
            await db_session.execute(
                select(OrderModel).where(OrderModel.status == OrderStatusEnum.PAID)
            )
        )
        .scalars()
        .first()
    )

    assert order is not None

    payment = PaymentModel(
        user_id=order.user_id,
        order_id=order.id,
        amount=order.total_amount,
        status=PaymentStatusEnum.SUCCESSFUL,
        external_payment_id="pi_test_456",
    )
    db_session.add(payment)
    await db_session.commit()

    headers = await get_headers(db_session, jwt_manager)
    response = await client.get("/payments/", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(p["id"] == payment.id for p in data)


@pytest.mark.asyncio
async def test_get_payment_detail_success(client, db_session, jwt_manager):
    """
    GET /payments/{payment_id} returns a single payment
    """

    payment = PaymentModel(
        user_id=1,
        order_id=1,
        amount=Decimal("15.00"),
        status=PaymentStatusEnum.SUCCESSFUL,
        external_payment_id="pi_test_789",
    )
    db_session.add(payment)
    await db_session.commit()

    headers = await get_headers(db_session, jwt_manager)

    response = await client.get(f"/payments/{payment.id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == payment.id
    assert Decimal(data["amount"]) == payment.amount


@pytest.mark.asyncio
async def test_get_payment_detail_not_found(client, db_session, jwt_manager):
    """
    GET /payments/{payment_id} returns 404 if payment does not exist
    """
    headers = await get_headers(db_session, jwt_manager)
    response = await client.get("/payments/9999999", headers=headers)
    assert response.status_code == 404
