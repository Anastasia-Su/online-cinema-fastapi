import pytest
from sqlalchemy import select

from src.database import MovieLikeModel, MovieModel, UserModel
from ..utils import make_token
from src.tasks.redis_blacklist import get_redis
from src.main import app

@pytest.mark.asyncio
async def test_like_movie(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    movie_id = 1
    

    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)
    
    resp = await client.post(f"/movies/{movie_id}/like", headers=headers)
    assert resp.status_code == 204

    # Verify DB state
    stmt = select(MovieLikeModel).where(
        MovieLikeModel.c.user_id == 3,
        MovieLikeModel.c.movie_id == movie_id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is not None
    assert row.like is True

    movie = await db_session.get(MovieModel, movie_id)
    assert movie.like_count == 1
    
    # app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dislike_movie(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    movie_id = 2
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)

    resp = await client.post(f"/movies/{movie_id}/dislike", headers=headers)
    assert resp.status_code == 204

    stmt = select(MovieLikeModel).where(
        MovieLikeModel.c.user_id == 3,
        MovieLikeModel.c.movie_id == movie_id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is not None
    assert row.like is False
    
    # app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_toggle_like_overwrite_dislike(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    movie_id = 3
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)

    # First dislike
    await client.post(f"/movies/{movie_id}/dislike", headers=headers)

    # Then like
    resp = await client.post(f"/movies/{movie_id}/like", headers=headers)
    assert resp.status_code == 204

    stmt = select(MovieLikeModel.c.like).where(
        MovieLikeModel.c.user_id == 3,
        MovieLikeModel.c.movie_id == movie_id,
    )
    value = (await db_session.execute(stmt)).scalar_one()
    assert value is True
    
    # app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_remove_reaction(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    movie_id = 4
    
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)

    # Like first
    await client.post(f"/movies/{movie_id}/like", headers=headers)

    # Now remove reaction
    resp = await client.delete(f"/movies/{movie_id}/reaction", headers=headers)
    assert resp.status_code == 204

    stmt = select(MovieLikeModel).where(
        MovieLikeModel.c.user_id == 3,
        MovieLikeModel.c.movie_id == movie_id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is None

    movie = await db_session.get(MovieModel, movie_id)
    assert movie.like_count == 0
    
    # app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_remove_reaction_not_exists(client, db_session, jwt_manager):
    # app.dependency_overrides[get_redis] = lambda: fake_redis
    stmt = select(UserModel).where(UserModel.group_id == 1)
    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)
    
    resp = await client.delete("/movies/9999/reaction", headers=headers)
    assert resp.status_code == 404
    
    # app.dependency_overrides.clear()
    