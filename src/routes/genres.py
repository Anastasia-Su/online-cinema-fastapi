from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.database import get_db, GenreModel, MovieGenreModel
from src.database.models.movies.movies_base import MovieModel
from src.schemas import GenreListResponseSchema, GenreCountSchema, MovieListResponseSchema
from .utils import SortBy, SortOrder

router = APIRouter(prefix="/genres", tags=["genres"])

@router.get(
    "/",
    response_model=GenreListResponseSchema,
    summary="List all genres with their movie counts",
)
async def get_genre_list(db: AsyncSession = Depends(get_db)) -> GenreListResponseSchema:
    stmt = (
        select(
            GenreModel,
            func.count(MovieGenreModel.c.movie_id).label("movie_count")
        )
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
                movie_count=genre.movie_count
            )
            for genre in genres
        ]
    )

@router.get(
    "/{genre_id}/movies/",
    response_model=MovieListResponseSchema,
    summary="List movies for a specific genre with pagination and sorting",
)
async def get_genre_movies(
    genre_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    sort_by: SortBy = Query(SortBy.IMDB, description="Sort by attribute: price, year, imdb, votes"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order: asc or desc"),
    db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    # Verify genre exists
    genre_exists = await db.execute(select(GenreModel).where(GenreModel.id == genre_id))
    if not genre_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Genre not found")

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No movies found for this genre.")

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

    paginated_stmt = stmt.order_by(sort_func(sort_column)).offset(offset).limit(per_page)
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