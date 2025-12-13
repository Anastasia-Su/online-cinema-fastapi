import pytest
from sqlalchemy import select

from src.database import MovieLikeModel, MovieModel
from ..utils import get_headers


@pytest.mark.asyncio
async def test_like_movie(client, db_session, jwt_manager):
    movie_id = 1
    headers = await get_headers(db_session, jwt_manager)

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


@pytest.mark.asyncio
async def test_dislike_movie(client, db_session, jwt_manager):
    movie_id = 2
    headers = await get_headers(db_session, jwt_manager)

    resp = await client.post(f"/movies/{movie_id}/dislike", headers=headers)
    assert resp.status_code == 204

    stmt = select(MovieLikeModel).where(
        MovieLikeModel.c.user_id == 3,
        MovieLikeModel.c.movie_id == movie_id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is not None
    assert row.like is False


@pytest.mark.asyncio
async def test_toggle_like_overwrite_dislike(client, db_session, jwt_manager):
    movie_id = 3
    headers = await get_headers(db_session, jwt_manager)

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


@pytest.mark.asyncio
async def test_remove_reaction(client, db_session, jwt_manager):
    movie_id = 4
    headers = await get_headers(db_session, jwt_manager)

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


@pytest.mark.asyncio
async def test_remove_reaction_not_exists(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    resp = await client.delete("/movies/9999/reaction", headers=headers)
    assert resp.status_code == 404
