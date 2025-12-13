import pytest
from ..utils import get_headers


@pytest.mark.asyncio
async def test_get_empty_cart(client, db_session, jwt_manager):
    """Cart is auto-created."""

    headers = await get_headers(db_session, jwt_manager)
    response = await client.get("/cart/", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_add_movie_to_cart(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    response = await client.post("/cart/add", json={"movie_id": 1}, headers=headers)
    assert response.status_code == 201

    cart = await client.get("/cart/", headers=headers)
    assert cart.status_code == 200
    assert cart.json()["items"][0].get("movie").get("id") == 1


@pytest.mark.asyncio
async def test_add_nonexistent_movie(client, jwt_manager, db_session):
    headers = await get_headers(db_session, jwt_manager)
    response = await client.post("/cart/add", json={"movie_id": 9999}, headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_movie_twice(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    response1 = await client.post("/cart/add", json={"movie_id": 2}, headers=headers)
    assert response1.status_code == 201

    response2 = await client.post("/cart/add", json={"movie_id": 2}, headers=headers)
    assert response2.status_code == 400
    assert response2.json()["detail"] == "Movie is already in the cart."


@pytest.mark.asyncio
async def test_remove_item(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    await client.post("/cart/add", json={"movie_id": 3}, headers=headers)

    response = await client.delete("/cart/remove/3", headers=headers)
    assert response.status_code == 204

    cart = await client.get("/cart/", headers=headers)
    assert cart.json()["items"] == []


@pytest.mark.asyncio
async def test_remove_nonexistent_item(client, jwt_manager, db_session):
    headers = await get_headers(db_session, jwt_manager)

    response = await client.delete("/cart/remove/1234", headers=headers)
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
async def test_get_cart_access_control(
    client, db_session, jwt_manager, role, expected_status
):
    user_headers = await get_headers(db_session, jwt_manager)
    await client.post("/cart/add", json={"movie_id": 3}, headers=user_headers)

    if role == "admin":
        group_id = 3
    elif role == "moderator":
        group_id = 2
    else:
        group_id = 1

    headers = await get_headers(db_session, jwt_manager, group_id)
    response = await client.get("/admin/cart/3", headers=headers)

    assert (
        response.status_code == expected_status
    ), f"Role '{role}' expected {expected_status}, got {response.status_code}, respp: {response}"
