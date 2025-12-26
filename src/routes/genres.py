from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.database import get_db, GenreModel, MovieGenreModel
from src.database.models.movies.movies_base import MovieModel
from src.schemas import (
    GenreListResponseSchema,
    GenreCountSchema,
    MovieListResponseSchema,
)
from .utils import SortBy, SortOrder

router = APIRouter(prefix="/genres", tags=["genres"])


@router.get(
    "/",
    response_model=GenreListResponseSchema,
    summary="List all genres with their movie counts",
    description=(
        "Retrieve a list of all movie genres along with the total number of movies "
        "associated with each genre."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Genres retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "genres": [
                            {"id": 1, "name": "Action", "movie_count": 42},
                            {"id": 2, "name": "Drama", "movie_count": 37},
                        ]
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - Failed to retrieve genres",
            "content": {
                "application/json": {
                    "example": {"detail": "An unexpected error occurred."}
                }
            },
        },
    },
)
async def get_genre_list(db: AsyncSession = Depends(get_db)) -> GenreListResponseSchema:
    """
    Retrieve all genres with aggregated movie counts.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        GenreListResponseSchema: List of genres with movie counts.
    """

    stmt = (
        select(GenreModel, func.count(MovieGenreModel.c.movie_id).label("movie_count"))
        .outerjoin(MovieGenreModel, GenreModel.id == MovieGenreModel.c.genre_id)
        .group_by(GenreModel.id)
        .order_by(GenreModel.name)
    )

    result = await db.execute(stmt)
    genres = result.all()

    return GenreListResponseSchema(
        genres=[
            GenreCountSchema(
                id=genre.GenreModel.id,
                name=genre.GenreModel.name,
                movie_count=genre.movie_count,
            )
            for genre in genres
        ]
    )


@router.get(
    "/{genre_id}/movies/",
    response_model=MovieListResponseSchema,
    summary="List movies for a specific genre with pagination and sorting",
    description=(
        "Retrieve a paginated and sortable list of movies that belong to a specific genre. "
        "Supports sorting by price, year, IMDb rating, votes, and duration."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Movies retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "movies": [
                            {
                                "id": 101,
                                "title": "Inception",
                                "year": 2010,
                                "imdb": 8.8,
                                "votes": 2200000,
                                "price": "9.99",
                                "time": 148,
                            }
                        ],
                        "prev_page": None,
                        "next_page": "/genres/1/movies/?page=2&per_page=10&sort_by=imdb&sort_order=desc",
                        "total_pages": 5,
                        "total_items": 42,
                    }
                }
            },
        },
        404: {
            "description": "Genre or movies not found",
            "content": {
                "application/json": {
                    "examples": {
                        "genre_not_found": {
                            "summary": "Genre not found",
                            "value": {"detail": "Genre not found"},
                        },
                        "no_movies": {
                            "summary": "No movies for genre",
                            "value": {"detail": "No movies found for this genre."},
                        },
                        "page_not_found": {
                            "summary": "Invalid page",
                            "value": {
                                "detail": "Page 3 not found. Total pages available: 2."
                            },
                        },
                    }
                }
            },
        },
        422: {
            "description": "Validation Error - Invalid query parameters",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["query", "per_page"],
                                "msg": "ensure this value is less than or equal to 20",
                                "type": "value_error.number.not_le",
                            }
                        ]
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - Failed to retrieve movies",
            "content": {
                "application/json": {
                    "example": {"detail": "An unexpected error occurred."}
                }
            },
        },
    },
)
async def get_genre_movies(
    genre_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    sort_by: SortBy = Query(
        SortBy.IMDB, description="Sort by attribute: price, year, imdb, votes"
    ),
    sort_order: SortOrder = Query(
        SortOrder.DESC, description="Sort order: asc or desc"
    ),
    db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Retrieve movies belonging to a specific genre.

    Applies pagination and sorting. Validates genre existence
    and page boundaries before returning results.

    Args:
        genre_id (int): Genre identifier.
        page (int): Page number.
        per_page (int): Items per page.
        sort_by (SortBy): Sorting field.
        sort_order (SortOrder): Sorting direction.
        db (AsyncSession): Asynchronous database session.

    Returns:
        MovieListResponseSchema: Paginated list of movies.
    """

    # Verify genre exists
    genre_exists = await db.execute(select(GenreModel).where(GenreModel.id == genre_id))
    if not genre_exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Genre not found"
        )

    # Build query for movies in the genre
    stmt = (
        select(MovieModel)
        .join(MovieGenreModel, MovieGenreModel.c.movie_id == MovieModel.id)
        .where(MovieGenreModel.c.genre_id == genre_id)
    )

    # Count total items
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = (await db.execute(count_stmt)).scalar_one()

    if total_items == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No movies found for this genre.",
        )

    total_pages = (total_items + per_page - 1) // per_page
    offset = (page - 1) * per_page

    if page > total_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page} not found. Total pages available: {total_pages}.",
        )

    # Sorting
    sort_column = {
        SortBy.PRICE: MovieModel.price,
        SortBy.YEAR: MovieModel.year,
        SortBy.IMDB: MovieModel.imdb,
        SortBy.VOTES: MovieModel.votes,
        SortBy.TIME: MovieModel.time,
    }[sort_by]
    sort_func = asc if sort_order == SortOrder.ASC else desc

    paginated_stmt = (
        stmt.order_by(sort_func(sort_column)).offset(offset).limit(per_page)
    )
    result = await db.execute(paginated_stmt)
    movies = result.scalars().all()

    # Build pagination links
    base_url = f"/genres/{genre_id}/movies/"
    prev_page = next_page = None
    if page > 1:
        prev_page = f"{base_url}?page={page-1}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}"
    if page < total_pages:
        next_page = f"{base_url}?page={page+1}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}"

    return MovieListResponseSchema(
        movies=movies,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )
