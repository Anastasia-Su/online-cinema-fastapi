from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy import select, func, and_, asc, desc, insert, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional


from src.database import (
    GenreModel,
    StarModel,
    DirectorModel,
    UserModel,
    MovieModel,
    MovieDirectorModel,
    MovieStarModel,
    MovieGenreModel,
    UserFavoriteMovieModel,
    MovieLikeModel,
    get_db,
    # get_current_user,
)

# from src.database.session_db import get_current_user
from src.config.get_current_user import get_current_user
from src.schemas import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema
from src.schemas.movies import MovieCreateSchema, MovieUpdateSchema
from ..utils import SortBy, SortOrder, toggle_movie_reaction, increment_counter


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post(
    "/{movie_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Like a movie",
    description="Adds a like from the current user to the specified movie.",
    responses={
        204: {
            "description": "Movie liked successfully.",
            "content": {"application/json": {"example": {}}},
        },
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
    },
)
async def like_movie(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Endpoint to like a movie.

    Args:
        movie_id (int): ID of the movie to like.
        user (UserModel): Current authenticated user.
        db (AsyncSession): Database session.

    Returns:
        Response: 204 No Content
    """

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
        )

    await toggle_movie_reaction(db, user.id, movie_id, is_like=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{movie_id}/dislike",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dislike a movie",
    description="Adds a dislike from the current user to the specified movie.",
    responses={
        204: {
            "description": "Movie disliked successfully.",
            "content": {"application/json": {"example": {}}},
        },
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {"example": {"detail": "Movie not found."}}
            },
        },
    },
)
async def dislike_movie(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Endpoint to dislike a movie.

    Args:
        movie_id (int): ID of the movie to dislike.
        user (UserModel): Current authenticated user.
        db (AsyncSession): Database session.

    Returns:
        Response: 204 No Content
    """

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
        )
    await toggle_movie_reaction(db, user.id, movie_id, is_like=False)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{movie_id}/reaction",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove reaction from a movie",
    description="Removes a like or dislike from the current user for the specified movie.",
    responses={
        204: {
            "description": "Reaction removed successfully.",
            "content": {"application/json": {"example": {}}},
        },
        404: {
            "description": "Movie not found or no reaction exists.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Movie does not have your reaction or does not exist"
                    }
                }
            },
        },
    },
)
async def remove_reaction(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Remove user's like/dislike from a movie.

    Args:
        movie_id (int): ID of the movie.
        user (UserModel): Current authenticated user.
        db (AsyncSession): Database session.

    Raises:
        HTTPException: 404 if the reaction does not exist.

    Returns:
        Response: 204 No Content
    """

    previous = await db.scalar(
        select(MovieLikeModel.c.like).where(
            MovieLikeModel.c.user_id == user.id, MovieLikeModel.c.movie_id == movie_id
        )
    )

    stmt = delete(MovieLikeModel).where(
        MovieLikeModel.c.user_id == user.id,
        MovieLikeModel.c.movie_id == movie_id,
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie does not have your reaction or does not exist",
        )

    if previous is True:
        await increment_counter(db, movie_id, "like_count", -1)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{movie_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add movie to favorites",
    description="Adds the specified movie to the current user's favorites.",
    responses={
        204: {
            "description": "Movie added to favorites.",
            "content": {"application/json": {"example": {}}},
        },
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with id X does not exist."}
                }
            },
        },
        409: {
            "description": "Movie already in favorites.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie is already in your favorites."}
                }
            },
        },
    },
)
async def add_to_favorites(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Add a movie to favorites.

    Args:
        movie_id (int): ID of the movie.
        user (UserModel): Current authenticated user.
        db (AsyncSession): Database session.

    Raises:
        HTTPException: 404 if the movie does not exist.
        HTTPException: 409 if movie already in favorites.

    Returns:
        Response: 204 No Content
    """

    movie_exists = await db.execute(
        select(MovieModel.id).where(MovieModel.id == movie_id)
    )
    if not movie_exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movie with id {movie_id} does not exist.",
        )
    already_favorited = await db.execute(
        select(UserFavoriteMovieModel).where(
            UserFavoriteMovieModel.c.user_id == user.id,
            UserFavoriteMovieModel.c.movie_id == movie_id,
        )
    )
    if already_favorited.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie is already in your favorites.",
        )

    stmt = insert(UserFavoriteMovieModel).values(user_id=user.id, movie_id=movie_id)
    await db.execute(stmt)

    await increment_counter(db, movie_id, "favorite_count", +1)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{movie_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove movie from favorites",
    description="Removes the specified movie from the current user's favorites.",
    responses={
        204: {
            "description": "Movie removed from favorites.",
            "content": {"application/json": {"example": {}}},
        },
        404: {
            "description": "Movie not in favorites or does not exist.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie is not in favorites or does not exist"}
                }
            },
        },
    },
)
async def remove_from_favorites(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Remove a movie from favorites.

    Args:
        movie_id (int): ID of the movie.
        user (UserModel): Current authenticated user.
        db (AsyncSession): Database session.

    Raises:
        HTTPException: 404 if movie not in favorites.

    Returns:
        Response: 204 No Content
    """

    stmt = delete(UserFavoriteMovieModel).where(
        UserFavoriteMovieModel.c.movie_id == movie_id,
        UserFavoriteMovieModel.c.user_id == user.id,
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie is not in favorites or does not exist",
        )
    await increment_counter(db, movie_id, "favorite_count", -1)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/favorites",
    response_model=MovieListResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get user's favorite movies",
    description=(
        "Returns a paginated list of movies added to the authenticated user's favorites. "
        "Supports optional filtering by movie title. "
        "If no favorite movies exist, an empty list with zero totals is returned."
    ),
    responses={
        200: {
            "description": "Favorite movies retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "with_results": {
                            "summary": "Favorites list with movies",
                            "value": {
                                "movies": [
                                    {
                                        "id": 1,
                                        "name": "Inception",
                                        "year": 2010,
                                        "rating": 8.8,
                                    }
                                ],
                                "prev_page": None,
                                "next_page": "/movies/favorites?page=2&per_page=10",
                                "total_pages": 2,
                                "total_items": 11,
                            },
                        },
                        "empty_favorites": {
                            "summary": "No favorite movies",
                            "value": {
                                "movies": [],
                                "prev_page": None,
                                "next_page": None,
                                "total_pages": 0,
                                "total_items": 0,
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "Page not found",
            "content": {"application/json": {"example": {"detail": "Page not found"}}},
        },
        401: {
            "description": "Unauthorized",
            "content": {"application/json": {"example": {"detail": "Unauthorized"}}},
        },
    },
)
async def get_favorites(
    user: UserModel = Depends(get_current_user),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    title: Optional[str] = Query(None, description="Search by movie title"),
    db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Retrieve the authenticated user's favorite movies.

    Behavior:
    - Returns paginated favorite movies.
    - Supports optional title-based filtering.
    - Returns an empty result set if the user has no favorites.
    - Raises 404 if the requested page exceeds total pages.

    Args:
        user (UserModel): Authenticated user.
        page (int): Page number (1-based).
        per_page (int): Number of movies per page.
        title (Optional[str]): Optional movie title filter.
        db (AsyncSession): Database session.

    Returns:
        MovieListResponseSchema: Paginated list of favorite movies.
    """

    stmt = (
        select(MovieModel)
        .join(
            UserFavoriteMovieModel, UserFavoriteMovieModel.c.movie_id == MovieModel.id
        )
        .where(UserFavoriteMovieModel.c.user_id == user.id)
        .distinct()
    )

    if title:
        stmt = stmt.where(MovieModel.name.ilike(f"%{title}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = (await db.execute(count_stmt)).scalar_one()

    if total_items == 0:
        return MovieListResponseSchema(
            movies=[],
            prev_page=None,
            next_page=None,
            total_pages=0,
            total_items=0,
        )

    total_pages = (total_items + per_page - 1) // per_page
    if page > total_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )

    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    movies = result.scalars().all()

    base_url = "/movies/favorites"
    query_params = {
        "per_page": per_page,
    }
    if title:
        query_params["title"] = title

    def build_url(page_num: int) -> str:
        params = "&".join(
            f"{k}={v}" for k, v in {**query_params, "page": page_num}.items()
        )
        return f"{base_url}?{params}"

    prev_page = build_url(page - 1) if page > 1 else None
    next_page = build_url(page + 1) if page < total_pages else None

    return MovieListResponseSchema(
        movies=[MovieListItemSchema.model_validate(movie) for movie in movies],
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )
