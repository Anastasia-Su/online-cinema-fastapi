import pytest
from decimal import Decimal
from ..utils import get_headers


@pytest.mark.asyncio
async def test_place_order_success(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    await client.post("/cart/add", json={"movie_id": 1}, headers=headers)
    await client.post("/cart/add", json={"movie_id": 2}, headers=headers)

    response = await client.post("/orders/", headers=headers)

    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "pending"
    assert len(data["items"]) == 2
    assert {item["movie"]["id"] for item in data["items"]} == {1, 2}
    assert Decimal(str(data["total_amount"])) > 0


@pytest.mark.asyncio
async def test_place_order_empty_cart(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    response = await client.post("/orders/", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Cart is empty."


@pytest.mark.asyncio
async def test_get_user_orders(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    # await client.post("/cart/add", json={"movie_id": 1}, headers=headers)
    # await client.post("/orders/", headers=headers)

    response = await client.get("/orders/", headers=headers)

    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2


@pytest.mark.asyncio
async def test_cancel_pending_order(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    await client.post("/cart/add", json={"movie_id": 2}, headers=headers)
    order_resp = await client.post("/orders/", headers=headers)
    order_id = order_resp.json()["id"]

    response = await client.post(f"/orders/{order_id}/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Order canceled successfully."


@pytest.mark.asyncio
async def test_cancel_order_not_found(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    response = await client.post("/orders/99999/cancel", headers=headers)

    assert response.status_code == 404


@pytest.mark.parametrize(
    "role,expected_status",
    [
        ("admin", 200),
        ("moderator", 403),
        ("user", 403),
    ],
)
@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_orders_access_control(
    client, db_session, jwt_manager, role, expected_status
):
    if role == "admin":
        group_id = 3
    elif role == "moderator":
        group_id = 2
    else:
        group_id = 1

    headers = await get_headers(db_session, jwt_manager, group_id)

    response = await client.get("/admin/orders", headers=headers)

    assert response.status_code == expected_status


@pytest.mark.asyncio
async def test_admin_list_orders_with_filters(client, db_session, jwt_manager):
    admin_headers = await get_headers(db_session, jwt_manager, group_id=3)

    response = await client.get("/admin/orders?status=pending", headers=admin_headers)

    assert response.status_code == 200
    assert isinstance(response.json(), list)
