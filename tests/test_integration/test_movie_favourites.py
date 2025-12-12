import pytest
from sqlalchemy import select

from src.database import (
    UserFavoriteMovieModel,
    MovieModel,
    UserModel
)
from src.tasks.redis_blacklist import get_redis
from src.main import app
from ..utils import make_token



@pytest.mark.asyncio
async def test_add_to_favorites(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)
    
    movie_id = 10

    resp = await client.post(f"/movies/{movie_id}/favorite", headers=headers)
    assert resp.status_code == 204

    stmt = select(UserFavoriteMovieModel).where(
        UserFavoriteMovieModel.c.user_id == 3,
        UserFavoriteMovieModel.c.movie_id == movie_id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is not None

    movie = await db_session.get(MovieModel, movie_id)
    assert movie.favorite_count == 1
    # app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_cannot_favorite_twice(client, jwt_manager, db_session):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    
    movie_id = 11
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)

    await client.post(f"/movies/{movie_id}/favorite", headers=headers)
    resp = await client.post(f"/movies/{movie_id}/favorite", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Movie is already in your favorites."
    # app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_remove_from_favorites(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    
    movie_id = 12
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)

    await client.post(f"/movies/{movie_id}/favorite", headers=headers)

    resp = await client.delete(f"/movies/{movie_id}/favorite", headers=headers)
    assert resp.status_code == 204

    stmt = select(UserFavoriteMovieModel).where(
        UserFavoriteMovieModel.c.user_id == 3,
        UserFavoriteMovieModel.c.movie_id == movie_id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is None

    movie = await db_session.get(MovieModel, movie_id)
    assert movie.favorite_count == 0
    # app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_remove_from_favorites_not_exists(client, jwt_manager, db_session):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)
    resp = await client.delete("/movies/9999/favorite", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Movie is not in favorites or does not exist"
    # app.dependency_overrides.clear()
    
    
@pytest.mark.asyncio
async def test_get_favorites_pagination(client, db_session, jwt_manager):
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)

    for movie_id in [1, 2, 3]:
        await client.post(f"/movies/{movie_id}/favorite", headers=headers)

    resp = await client.get("/movies/favorites?page=1&per_page=2", headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert len(data["movies"]) == 2
    assert data["total_items"] == 3
    assert data["total_pages"] == 2
    assert data["next_page"] is not None
