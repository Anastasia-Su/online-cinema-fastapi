import pytest
from sqlalchemy import select

from src.database import (
    MovieCommentModel,
    CommentLikeModel,
    MovieModel,
)
from ..utils import get_headers

@pytest.mark.asyncio
async def test_create_comment(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 1

    payload = {"content": "Great movie!"}
    resp = await client.post(
        f"/movies/{movie_id}/comments",
        json=payload,
        headers=headers,
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Great movie!"
    assert data["movie_id"] == movie_id
    assert data["parent_id"] is None
    assert data["like_count"] == 0

    stmt = select(MovieCommentModel).where(
        MovieCommentModel.movie_id == movie_id,
        MovieCommentModel.user_id == 3,
    )
    comment = (await db_session.execute(stmt)).scalar_one()
    assert comment.content == "Great movie!"

    movie = await db_session.get(MovieModel, movie_id)
    assert movie.comment_count == 1


@pytest.mark.asyncio
async def test_create_reply_comment(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 2

    parent = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Parent comment",
    )
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    payload = {
        "content": "Reply comment",
        "parent_id": parent.id,
    }

    resp = await client.post(
        f"/movies/{movie_id}/comments",
        json=payload,
        headers=headers,
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["parent_id"] == parent.id


@pytest.mark.asyncio
async def test_create_comment_invalid_parent(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    payload = {
        "content": "Reply",
        "parent_id": 9999,
    }

    resp = await client.post(
        "/movies/1/comments",
        json=payload,
        headers=headers,
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_movie_comments(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 3

    parent = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Top comment",
    )
    reply = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Reply",
        parent_id=1,  # fixed after flush
    )

    db_session.add(parent)
    await db_session.flush()
    reply.parent_id = parent.id
    db_session.add(reply)
    await db_session.commit()

    resp = await client.get(
        f"/movies/{movie_id}/comments",
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Top comment"
    assert len(data[0]["replies"]) == 1
    
    
@pytest.mark.asyncio
async def test_get_comment_by_id(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 4

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Single comment",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    resp = await client.get(
        f"/movies/{movie_id}/comments/{comment.id}",
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["content"] == "Single comment"


@pytest.mark.asyncio
async def test_update_comment(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 5

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Old content",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    payload = {"content": "Updated content"}
    resp = await client.patch(
        f"/movies/{movie_id}/comments/{comment.id}",
        json=payload,
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated content"

@pytest.mark.asyncio
async def test_update_comment_not_author(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 6

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=999,
        content="Other user comment",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    resp = await client.patch(
        f"/movies/{movie_id}/comments/{comment.id}",
        json={"content": "Hack"},
        headers=headers,
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_comment(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 7

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="To be deleted",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    resp = await client.delete(
        f"/movies/{movie_id}/comments/{comment.id}",
        headers=headers,
    )

    assert resp.status_code == 204

    stmt = select(MovieCommentModel).where(MovieCommentModel.id == comment.id)
    row = (await db_session.execute(stmt)).first()
    assert row is None


@pytest.mark.asyncio
async def test_like_comment(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 8

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Like me",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    resp = await client.post(
        f"/movies/{movie_id}/comments/{comment.id}/like",
        headers=headers,
    )

    assert resp.status_code == 204

    stmt = select(CommentLikeModel).where(
        CommentLikeModel.c.user_id == 3,
        CommentLikeModel.c.comment_id == comment.id,
    )
    row = (await db_session.execute(stmt)).first()
    assert row is not None

@pytest.mark.asyncio
async def test_like_comment_twice(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 9

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Like once",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    await client.post(
        f"/movies/{movie_id}/comments/{comment.id}/like",
        headers=headers,
    )
    resp = await client.post(
        f"/movies/{movie_id}/comments/{comment.id}/like",
        headers=headers,
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unlike_comment(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)
    movie_id = 10

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=3,
        content="Unlike me",
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    await client.post(
        f"/movies/{movie_id}/comments/{comment.id}/like",
        headers=headers,
    )

    resp = await client.delete(
        f"/movies/{movie_id}/comments/{comment.id}/like",
        headers=headers,
    )

    assert resp.status_code == 204

@pytest.mark.asyncio
async def test_unlike_comment_not_exists(client, db_session, jwt_manager):
    headers = await get_headers(db_session, jwt_manager)

    resp = await client.delete(
        "/movies/9/comments/999/like",
        headers=headers,
    )

    assert resp.status_code == 404



