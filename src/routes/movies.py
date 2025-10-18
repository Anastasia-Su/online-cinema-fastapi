from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from src.database import get_db, MovieModel
from src.database import (
    GenreModel,
    StarModel,
    DirectorModel
)
from src.schemas import (
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieDetailSchema
)
from src.schemas.movies import MovieCreateSchema, MovieUpdateSchema




router = APIRouter()


@router.get(
    "/movies/",
    response_model=MovieListResponseSchema,
    summary="Browse the movie catalog with pagination, filtering, and sorting",
)
async def get_movie_list(
    page: int = Query(1, ge=1, description="Page number (1-based index)"),
    per_page: int = Query(10, ge=1, le=20, description="Number of items per page"),
    # search: Optional[str] = Query(None, description="Search by title, description"),
    # min_imdb: Optional[float] = Query(None, description="Filter by minimum IMDb rating"),
    # max_imdb: Optional[float] = Query(None, description="Filter by maximum IMDb rating"),
    db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Fetch a paginated list of movies from the database (asynchronously).

    Allows filtering by IMDb rating and simple search by title or description.
    Pagination is done via offset + limit. Returns previous/next page URLs.
    """
    
    
    total_items = await db.execute(
        select(func.count()).select_from(MovieModel)
    )
    total_items = int(total_items.scalar_one())

    if total_items == 0:
        raise HTTPException(status_code=404, detail="No movies found.")

    total_pages = (total_items + per_page - 1) // per_page
    offset = (page - 1) * per_page

    result = await db.execute(
        select(MovieModel)
        .order_by(MovieModel.id)
        .offset(offset)
        .limit(per_page)
    )
    movies = result.scalars().all()

    if not movies:
        raise HTTPException(status_code=404, detail="No movies found.")

    base_url = "/movies/"
    prev_page: Optional[str] = None
    next_page: Optional[str] = None

    if page > 1:
        prev_page = f"{base_url}?page={page-1}&per_page={per_page}"
    if page < total_pages:
        next_page = f"{base_url}?page={page+1}&per_page={per_page}"

    return {
        "movies": movies,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "total_items": total_items,
    }

    # offset = (page - 1) * per_page

    # # Total items count
    # count_stmt = select(func.count(MovieModel.id))
    # result_count = await db.execute(count_stmt)
    # total_items = result_count.scalar() or 0

    # if not total_items:
    #     raise HTTPException(status_code=404, detail="No movies found.")

    # # Base query
    # stmt = select(MovieModel)

    # # Search / filtering
    # if search:
    #     search_pattern = f"%{search.lower()}%"
    #     stmt = stmt.where(
    #         MovieModel.name.ilike(search_pattern)
    #         | MovieModel.description.ilike(search_pattern)
    #     )
    # if min_imdb is not None:
    #     stmt = stmt.where(MovieModel.imdb >= min_imdb)
    # if max_imdb is not None:
    #     stmt = stmt.where(MovieModel.imdb <= max_imdb)

    # # Default ordering
    # order_by = MovieModel.default_order_by()
    # if order_by:
    #     stmt = stmt.order_by(*order_by)

    # # Pagination
    # stmt = stmt.offset(offset).limit(per_page)
    # result_movies = await db.execute(stmt)
    # movies = result_movies.scalars().all()

    # if not movies:
    #     raise HTTPException(status_code=404, detail="No movies found.")

    # movie_list = [MovieListItemSchema.model_validate(movie) for movie in movies]

    # total_pages = (total_items + per_page - 1) // per_page

    # response = MovieListResponseSchema(
    #     movies=movie_list,
    #     prev_page=f"/movies/?page={page - 1}&per_page={per_page}" if page > 1 else None,
    #     next_page=f"/movies/?page={page + 1}&per_page={per_page}" if page < total_pages else None,
    #     total_pages=total_pages,
    #     total_items=total_items,
    # )
    # return response
