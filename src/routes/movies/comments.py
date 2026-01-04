from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy import select, func, and_, delete, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, raiseload, selectinload, defaultload
from typing import Optional

from src.database import (
    MovieCommentModel,
    CommentLikeModel,
    UserModel,
    MovieModel,
    UserGroupEnum,
    get_db,
    # get_current_user,
)
from src.config.get_current_user import get_current_user
from src.schemas.comments import CommentCreateSchema, CommentUpdateSchema, CommentSchema

from ..utils import increment_counter
from src.tasks.comment_notifications import (
    send_comment_reply_email,
    send_comment_like_email,
)

# _: UserModel = Depends(require_moderator_or_admin),

router = APIRouter(prefix="/movies", tags=["movies"])


@router.post(
    "/{movie_id}/comments",
    response_model=CommentSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new comment for a movie",
    description=(
        "Create a new comment for a given movie. Optionally, the comment can be a reply to a parent comment. "
        "The endpoint validates that the movie exists and that the parent comment belongs to the same movie."
    ),
    responses={
        201: {
            "description": "Comment created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "content": "Great movie!",
                        "created_at": "2025-12-26T12:00:00",
                        "updated_at": None,
                        "movie_id": 42,
                        "user_id": 7,
                        "parent_id": None,
                        "username": "user@example.com",
                        "like_count": 0,
                        "user_has_liked": False,
                        "replies": [],
                    }
                }
            },
        },
        400: {
            "description": "Invalid parent comment",
            "content": {
                "application/json": {"example": {"detail": "Invalid parent comment"}}
            },
        },
        404: {
            "description": "Movie not found",
            "content": {"application/json": {"example": {"detail": "Movie not found"}}},
        },
    },
)
async def create_comment(
    movie_id: int,
    payload: CommentCreateSchema,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentSchema:
    """
    Create a comment for a specific movie.

    Steps:
    1. Validate that the movie exists.
    2. Create the comment with optional parent comment ID.
    3. Send notification if it is a reply.
    4. Load related user and likes for the comment.
    5. Increment movie's comment count.

    :param movie_id: The ID of the movie to comment on.
    :type movie_id: int
    :param payload: The content of the comment and optional parent_id.
    :type payload: CommentCreateSchema
    :param user: The current authenticated user.
    :type user: UserModel
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession
    :return: The created comment with replies and like information.
    :rtype: CommentSchema
    :raises HTTPException:
        - 400 if the parent comment is invalid.
        - 404 if the movie does not exist.
    """

    # Check movie exists
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found"
        )

    comment = MovieCommentModel(
        movie_id=movie_id,
        user_id=user.id,
        content=payload.content.strip(),
        parent_id=payload.parent_id,
    )
    db.add(comment)

    if payload.parent_id:
        parent = await db.get(MovieCommentModel, payload.parent_id)

        if not parent or parent.movie_id != movie_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent comment"
            )

    await db.flush()
    await db.refresh(comment)

    if payload.parent_id:
        send_comment_reply_email.delay(
            email=str(parent.user.email),
            parent_preview=str(parent.content),
            current_preview=str(comment.content),
            reply_link=f"http://127.0.0.1:8000/movies/{movie_id}/comments/{comment.id}",
        )

    await db.flush()
    await db.refresh(comment)

    # Load user and likes
    result = await db.execute(
        select(MovieCommentModel)
        .options(
            # selectinload(MovieCommentModel.user),
            selectinload(MovieCommentModel.liked_by_users),
            selectinload(
                MovieCommentModel.replies.and_(MovieCommentModel.liked_by_users)
            ),
        )
        .where(MovieCommentModel.id == comment.id)
    )
    comment = result.scalar_one()
    await increment_counter(db, movie_id, "comment_count", +1)
    await db.commit()

    return enrich_comment_sync(comment, user.id)


@router.get(
    "/{movie_id}/comments",
    response_model=list[CommentSchema],
    operation_id="get_movie_comments",
    summary="Get comments for a movie",
    description="Retrieve a paginated list of comments for a given movie.",
    responses={
        200: {
            "description": "List of comments for the movie",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": 1,
                            "content": "Great movie!",
                            "created_at": "2025-12-26T12:00:00",
                            "updated_at": None,
                            "movie_id": 42,
                            "user_id": 7,
                            "parent_id": None,
                            "username": "user@example.com",
                            "like_count": 0,
                            "user_has_liked": False,
                            "replies": [],
                        }
                    ]
                }
            },
        },
        404: {
            "description": "Movie not found",
            "content": {"application/json": {"example": {"detail": "Movie not found"}}},
        },
    },
)
async def get_comments(
    movie_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommentSchema]:
    """
    Retrieve comments for a specific movie with pagination.

    Steps:
    1. Validate that the movie exists.
    2. Fetch comments and related replies, users, and likes.
    3. Organize comments into top-level comments with nested replies.
    4. Return enriched comments with like information for the current user.

    :param movie_id: The ID of the movie.
    :type movie_id: int
    :param page: The page number (default 1).
    :type page: int
    :param per_page: Number of comments per page (default 10, max 50).
    :type per_page: int
    :param user: The current authenticated user.
    :type user: UserModel
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession
    :return: List of top-level comments with nested replies and like info.
    :rtype: List[CommentSchema]
    :raises HTTPException:
        - 404 if the movie does not exist.
    """

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found"
        )

    offset = (page - 1) * per_page

    stmt = (
        select(MovieCommentModel)
        .where(
            MovieCommentModel.movie_id == movie_id,
        )
        .order_by(MovieCommentModel.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .options(
            selectinload(MovieCommentModel.user),
            selectinload(MovieCommentModel.liked_by_users),
            selectinload(MovieCommentModel.replies).selectinload(
                MovieCommentModel.user
            ),
            selectinload(MovieCommentModel.replies).selectinload(
                MovieCommentModel.liked_by_users
            ),
        )
    )

    result = await db.execute(stmt)
    all_comments = result.scalars().unique().all()

    comment_map = {c.id: c for c in all_comments}
    for comment in all_comments:
        if comment.parent_id and comment.parent_id in comment_map:
            parent = comment_map[comment.parent_id]
            if not hasattr(parent, "replies"):
                parent.replies = []
            if comment not in parent.replies:
                parent.replies.append(comment)

    top_level_comments = [c for c in all_comments if c.parent_id is None]
    top_level_comments.sort(key=lambda c: c.created_at, reverse=True)

    # Reuse the same function!
    return [
        enrich_comment_sync(c, user.id)
        for c in top_level_comments[offset : offset + per_page]
    ]


@router.patch(
    "/{movie_id}/comments/{comment_id}",
    response_model=CommentSchema,
    summary="Update a comment",
    description="Update a user's comment content by its ID.",
    responses={
        200: {"description": "Comment updated successfully"},
        403: {
            "description": "Not authorized",
            "content": {"application/json": {"example": {"detail": "Not authorized"}}},
        },
        404: {
            "description": "Comment not found",
            "content": {
                "application/json": {"example": {"detail": "Comment not found"}}
            },
        },
    },
)
async def update_comment(
    movie_id: int,
    comment_id: int,
    payload: CommentUpdateSchema,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentSchema:
    """
    Update the content of a comment.

    :param movie_id: Movie ID of the comment.
    :param comment_id: Comment ID to update.
    :param payload: New content for the comment.
    :param user: Current authenticated user.
    :param db: Async database session.
    :return: Updated comment with replies and like information.
    :raises HTTPException:
        - 403 if user is not the author.
        - 404 if comment or movie not found.
    """

    comment = await db.get(MovieCommentModel, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if comment.movie_id != movie_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized"
        )

    comment.content = payload.content.strip()
    comment.updated_at = func.now()
    await db.commit()
    await db.refresh(comment)

    result = await db.execute(
        select(MovieCommentModel)
        .options(
            # joinedload(MovieCommentModel.liked_by_users)
            selectinload(MovieCommentModel.liked_by_users),
            selectinload(
                MovieCommentModel.replies.and_(MovieCommentModel.liked_by_users)
            ),
        )
        .where(MovieCommentModel.id == comment_id)
    )
    comment = result.scalars().first()

    return enrich_comment_sync(comment, user.id)


@router.get(
    "/{movie_id}/comments/{comment_id}",
    response_model=CommentSchema,
    summary="Get comment details by ID",
    description=(
        "Retrieve detailed information about a specific comment by its ID. "
        "Includes nested replies, user info, and like information."
    ),
    responses={
        200: {
            "description": "Comment retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "content": "Great movie!",
                        "created_at": "2025-12-26T12:00:00",
                        "updated_at": None,
                        "movie_id": 42,
                        "user_id": 7,
                        "parent_id": None,
                        "username": "user@example.com",
                        "like_count": 0,
                        "user_has_liked": False,
                        "replies": [],
                    }
                }
            },
        },
        404: {
            "description": "Comment not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Comment with the given ID was not found."}
                }
            },
        },
    },
)
async def get_comment_by_id(
    movie_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
) -> CommentSchema:
    """
    Retrieve detailed information about a specific comment by its ID.

    Steps:
    1. Load the comment with its user, likes, and replies.
    2. If not found, raise a 404 error.
    3. Enrich the comment with like information for the current user.

    :param comment_id: The ID of the comment to retrieve.
    :type comment_id: int
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession
    :return: The comment with nested replies and like info.
    :rtype: CommentSchema
    :raises HTTPException: 404 if the comment is not found.
    """

    stmt = (
        select(
            MovieCommentModel,
        )
        .options(
            selectinload(MovieCommentModel.liked_by_users),
            selectinload(
                MovieCommentModel.replies.and_(MovieCommentModel.liked_by_users)
            ),
        )
        .where(
            MovieCommentModel.id == comment_id,
            MovieCommentModel.movie_id == movie_id,
        )
    )

    result = await db.execute(stmt)
    comment = result.scalars().first()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment with the given ID was not found.",
        )

    return enrich_comment_sync(comment, comment.user_id)


@router.delete(
    "/{movie_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
    description="Delete a user's comment by its ID.",
    responses={
        204: {"description": "Comment deleted successfully"},
        403: {
            "description": "Not authorized",
            "content": {"application/json": {"example": {"detail": "Not authorized"}}},
        },
        404: {
            "description": "Comment not found",
            "content": {
                "application/json": {"example": {"detail": "Comment not found"}}
            },
        },
    },
)
async def delete_comment(
    movie_id: int,
    comment_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Delete a comment if the current user is the author.

    :param movie_id: ID of the movie.
    :param comment_id: ID of the comment.
    :param user: Current authenticated user.
    :param db: Async database session.
    :raises HTTPException:
        - 403 if user is not the author.
        - 404 if comment or movie not found.
    """

    comment = await db.get(MovieCommentModel, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if comment.movie_id != movie_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if comment.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized"
        )

    await db.delete(comment)
    await increment_counter(db, movie_id, "comment_count", -1)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{movie_id}/comments/{comment_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Like a comment",
    description="Add a like to a comment by the current user.",
    responses={
        204: {"description": "Comment liked successfully"},
        404: {
            "description": "Comment not found",
            "content": {
                "application/json": {"example": {"detail": "Comment not found"}}
            },
        },
    },
)
async def like_comment(
    movie_id: int,
    comment_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Like a specific comment.

    :param movie_id: Movie ID of the comment.
    :param comment_id: Comment ID to like.
    :param user: Current authenticated user.
    :param db: Async database session.
    :raises HTTPException: 404 if comment not found.
    """

    comment = await db.get(MovieCommentModel, comment_id)

    if not comment or comment.movie_id != movie_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    stmt = (
        insert(CommentLikeModel).values(user_id=user.id, comment_id=comment_id)
        # .on_conflict_do_nothing()
    )
    try:
        await db.execute(stmt)
        await db.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already liked this comment",
        )

    send_comment_like_email.delay(
        email=str(comment.user.email),
        parent_preview=str(comment.content),
        comment_link=f"http://127.0.0.1:8000/movies/{movie_id}/comments/{comment_id}",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{movie_id}/comments/{comment_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlike a comment",
    description="Remove the current user's like from a comment.",
    responses={
        204: {"description": "Comment unliked successfully"},
        404: {
            "description": "Like not found",
            "content": {"application/json": {"example": {"detail": "Like not found"}}},
        },
    },
)
async def unlike_comment(
    movie_id: int,
    comment_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Remove a like from a comment.

    :param movie_id: Movie ID of the comment.
    :param comment_id: Comment ID to unlike.
    :param user: Current authenticated user.
    :param db: Async database session.
    :raises HTTPException: 404 if like does not exist.
    """

    comment = await db.get(MovieCommentModel, comment_id)
    if not comment or comment.movie_id != movie_id:
        raise HTTPException(status_code=404, detail="Comment not found")

    stmt = delete(CommentLikeModel).where(
        CommentLikeModel.c.user_id == user.id,
        CommentLikeModel.c.comment_id == comment_id,
    )
    result = await db.execute(stmt)
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Like not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def enrich_comment_sync(
    comment: MovieCommentModel,
    current_user_id: int,
) -> CommentSchema:
    """
    Converts a fully-loaded MovieCommentModel → CommentSchema
    """
    return CommentSchema(
        id=comment.id,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        movie_id=comment.movie_id,
        user_id=comment.user_id,
        parent_id=comment.parent_id,
        username=comment.user.email,
        like_count=len(comment.liked_by_users),
        user_has_liked=current_user_id in {u.id for u in comment.liked_by_users},
        replies=[
            enrich_comment_sync(reply, current_user_id)
            for reply in getattr(comment, "replies", [])
        ],
    )
