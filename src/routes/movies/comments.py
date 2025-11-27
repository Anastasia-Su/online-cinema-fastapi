from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy import select, func, and_, delete, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, raiseload, selectinload, defaultload
from typing import Optional

from src.database import (
    MovieCommentModel,
    CommentLikeModel,
    UserModel,
    MovieModel,
    UserGroupEnum,
    get_db,
    get_current_user,
)
from src.schemas.comments import CommentCreateSchema, CommentUpdateSchema, CommentSchema
from ..admin import require_moderator_or_admin
from ..utils import increment_counter
from src.tasks.comment_notifications import send_comment_reply_email

# _: UserModel = Depends(require_moderator_or_admin),

router = APIRouter(prefix="/movies", tags=["movies"])


@router.post(
    "/{movie_id}/comments",
    response_model=CommentSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    movie_id: int,
    payload: CommentCreateSchema,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    await db.flush()
    await db.refresh(comment)
    
    # Validate parent comment belongs to same movie
    if payload.parent_id:
        parent = await db.get(MovieCommentModel, payload.parent_id)
        
        
        
        if not parent or parent.movie_id != movie_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent comment"
            )
        
            
        await send_comment_reply_email(
            email=parent.user.email,
                # recipient_email=parent.user.email,
                # recipient_username=parent.user.email,
                # actor_username=user.email,
                # movie_title=movie.name,
            parent_preview=parent.content,
            current_preview=comment.content,
            reply_link =  f"http://127.0.0.1:8000/movies/{movie_id}/{comment.id}",
            )
            
            
            


    # Load user and likes
    result = await db.execute(
        select(MovieCommentModel)
        .options(
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

    # return await enrich_comment(comment, user.id, db)
    return enrich_comment_sync(comment, user.id)


@router.get("/{movie_id}/comments", response_model=list[CommentSchema], operation_id="get_movie_comments")
async def get_comments(
    movie_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

            selectinload(MovieCommentModel.replies).selectinload(MovieCommentModel.user),
            selectinload(MovieCommentModel.replies).selectinload(MovieCommentModel.liked_by_users),
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
        for c in top_level_comments[offset:offset + per_page]
    ]

@router.patch("/{movie_id}/comments/{comment_id}", response_model=CommentSchema)
async def update_comment(
    movie_id: int,
    comment_id: int,
    payload: CommentUpdateSchema,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    "/{movie_id}/{comment_id}",
    response_model=CommentSchema,
    summary="Get comment details by ID",
)
async def get_comment_by_id(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve detailed information about a specific comment by its ID.
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
        .where(MovieCommentModel.id == comment_id)
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
    "/{movie_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_comment(
    movie_id: int,
    comment_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    "/{movie_id}/comments/{comment_id}/like", status_code=status.HTTP_204_NO_CONTENT
)
async def like_comment(
    movie_id: int,
    comment_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await db.get(MovieCommentModel, comment_id)
    if not comment or comment.movie_id != movie_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    stmt = (
        insert(CommentLikeModel)
        .values(user_id=user.id, comment_id=comment_id)
        # .on_conflict_do_nothing()
    )

    await db.execute(stmt)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{movie_id}/comments/{comment_id}/like", status_code=status.HTTP_204_NO_CONTENT
)
async def unlike_comment(
    movie_id: int,
    comment_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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