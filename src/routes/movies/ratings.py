from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select, update, insert, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.ratings import RatingCreateSchema, RatingSchema
from src.database import (
    MovieRatingModel,
    MovieModel,
    get_db,
    # get_current_user,
    UserModel,
)
from src.config.get_current_user import get_current_user
from ..utils import update_movie_rating_stats


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post(
    "/{movie_id}/rating",
    response_model=RatingSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Rate a movie",
    description=(
        "Creates or updates the current user's rating for the specified movie. "
        "If the user has already rated the movie, the existing rating is updated. "
        "Movie rating statistics are recalculated automatically."
    ),
    responses={
        201: {
            "description": "Rating created or updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "user_id": 5,
                        "movie_id": 12,
                        "rating": 8,
                        "created_at": "2025-01-01T12:00:00Z",
                        "updated_at": "2025-01-02T09:30:00Z",
                        "username": "user@example.com",
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
        404: {
            "description": "Movie not found",
            "content": {"application/json": {"example": {"detail": "Movie not found"}}},
        },
    },
)
async def rate_movie(
    movie_id: int,
    payload: RatingCreateSchema,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RatingSchema:
    """
    Create or update the authenticated user's rating for a movie.

    Behavior:
    - Inserts a new rating if none exists.
    - Updates the existing rating if already present.
    - Recalculates movie rating statistics after the change.

    Returns:
        RatingSchema: The user's rating for the movie.
    """

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found"
        )

    select_result = await db.execute(
        select(MovieRatingModel.rating).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    current_rating = select_result.scalar_one_or_none()

    update_stmt = (
        update(MovieRatingModel)
        .where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
        .values(rating=payload.rating, updated_at=func.now())
    )

    result = await db.execute(update_stmt)
    await db.flush()

    rating_obj = result.scalar_one_or_none()  # ← READ ONCE ONLY

    if not rating_obj:
        # INSERT
        insert_stmt = insert(MovieRatingModel).values(
            user_id=current_user.id,
            movie_id=movie_id,
            rating=payload.rating,
        )

        result = await db.execute(insert_stmt)
        await db.flush()
        rating_obj = result.scalar_one()

    await update_movie_rating_stats(
        db=db, movie_id=movie_id, old_rating=current_rating, new_rating=payload.rating
    )

    await db.commit()

    return RatingSchema(
        user_id=rating_obj.user_id,
        movie_id=rating_obj.movie_id,
        rating=rating_obj.rating,
        created_at=rating_obj.created_at,
        updated_at=rating_obj.updated_at,
        username=current_user.email,
    )


@router.get(
    "/{movie_id}/rating",
    response_model=RatingSchema,
    status_code=status.HTTP_200_OK,
    summary="Get my movie rating",
    description=(
        "Returns the authenticated user's rating for the specified movie. "
        "If the user has not rated the movie, an error is returned."
    ),
    responses={
        200: {
            "description": "Rating retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "user_id": 5,
                        "movie_id": 12,
                        "rating": 9,
                        "created_at": "2025-01-01T12:00:00Z",
                        "updated_at": None,
                        "username": "user@example.com",
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
        404: {
            "description": "Rating not found",
            "content": {
                "application/json": {
                    "example": {"detail": "You haven't rated this movie yet"}
                }
            },
        },
    },
)
async def get_my_rating(
    movie_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RatingSchema:
    """
    Retrieve the authenticated user's rating for a movie.

    Behavior:
    - Returns the rating if it exists.
    - Raises 404 if the user has not rated the movie.

    Returns:
        RatingSchema: The user's movie rating.
    """

    result = await db.execute(
        select(MovieRatingModel).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You haven't rated this movie yet",
        )

    return RatingSchema(
        user_id=rating.user_id,
        movie_id=rating.movie_id,
        rating=rating.rating,
        created_at=rating.created_at,
        updated_at=rating.updated_at,
        username=current_user.email,
    )


@router.delete(
    "/{movie_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete my movie rating",
    description=(
        "Deletes the authenticated user's rating for the specified movie. "
        "Movie rating statistics are recalculated after deletion."
    ),
    responses={
        204: {"description": "Rating deleted successfully"},
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
        404: {
            "description": "Rating not found",
            "content": {
                "application/json": {
                    "examples": {
                        "no_rating": {
                            "summary": "No rating exists",
                            "value": {"detail": "You haven't rated this movie"},
                        },
                        "rating_missing": {
                            "summary": "Rating not found during deletion",
                            "value": {"detail": "Rating not found"},
                        },
                    }
                }
            },
        },
    },
)
async def delete_rating(
    movie_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Delete the authenticated user's rating for a movie.

    Behavior:
    - Removes the rating if it exists.
    - Recalculates movie rating statistics.
    - Returns 204 with no response body.

    Returns:
        Response: Empty 204 NO CONTENT response.
    """

    current_rating_result = await db.execute(
        select(MovieRatingModel.rating).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    current_rating = current_rating_result.scalar_one_or_none()

    if current_rating is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="You haven't rated this movie"
        )

    result = await db.execute(
        delete(MovieRatingModel).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )

    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rating not found"
        )

    await update_movie_rating_stats(
        db=db, movie_id=movie_id, old_rating=current_rating, new_rating=None
    )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
