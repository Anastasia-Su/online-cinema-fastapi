from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional


from src.database import (
    GenreModel,
    StarModel,
    DirectorModel,
    MovieModel,
    MovieDirectorModel,
    MovieStarModel,
    MovieGenreModel,
    get_db,
)
from src.schemas import MovieListResponseSchema, MovieDetailSchema
from ..utils import SortBy, SortOrder


router = APIRouter(prefix="/movies", tags=["movies"])


@router.get(
    "/",
    response_model=MovieListResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Browse movie catalog",
    description=(
        "Returns a paginated list of movies with support for searching, filtering, "
        "and sorting. Multiple filters can be combined. "
        "Raises an error if no movies match the given criteria or if the requested "
        "page is out of range."
    ),
    responses={
        200: {
            "description": "Movies retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "with_results": {
                            "summary": "Movies list",
                            "value": {
                                "movies": [
                                    {
                                        "id": 1,
                                        "name": "Inception",
                                        "year": 2010,
                                        "imdb": 8.8,
                                    }
                                ],
                                "prev_page": None,
                                "next_page": "/movies/?page=2&per_page=10",
                                "total_pages": 3,
                                "total_items": 21,
                            },
                        }
                    }
                }
            },
        },
        400: {
            "description": "Invalid filter values",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_year_range": {
                            "summary": "Invalid year range",
                            "value": {
                                "detail": "year_min must be less than or equal to year_max"
                            },
                        },
                        "invalid_imdb_range": {
                            "summary": "Invalid IMDb range",
                            "value": {
                                "detail": "imdb_min must be less than or equal to imdb_max"
                            },
                        },
                        "invalid_price_range": {
                            "summary": "Invalid price range",
                            "value": {
                                "detail": "price_min must be less than or equal to price_max"
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "No movies found or page out of range",
            "content": {
                "application/json": {
                    "examples": {
                        "no_movies": {
                            "summary": "No movies match filters",
                            "value": {"detail": "No movies found."},
                        },
                        "page_not_found": {
                            "summary": "Invalid page",
                            "value": {
                                "detail": "Page 5 not found. Total pages available: 3."
                            },
                        },
                    }
                }
            },
        },
    },
)
async def get_movie_list(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    title: Optional[str] = Query(None, description="Search by movie title"),
    description: Optional[str] = Query(None, description="Search by movie description"),
    actor: Optional[str] = Query(None, description="Search by actor name"),
    director: Optional[str] = Query(None, description="Search by director name"),
    genre: Optional[str] = Query(
        None, min_length=2, description="Filter by genre name"
    ),
    sort_by: SortBy = Query(
        SortBy.IMDB, description="Sort by attribute: price, year, imdb, votes"
    ),
    sort_order: SortOrder = Query(
        SortOrder.DESC, description="Sort order: asc or desc"
    ),
    year_min: Optional[int] = Query(None, ge=1895, description="Minimum release year"),
    year_max: Optional[int] = Query(None, le=2025, description="Maximum release year"),
    imdb_min: Optional[float] = Query(
        None, ge=0.0, le=10.0, description="Minimum IMDb rating"
    ),
    imdb_max: Optional[float] = Query(
        None, ge=0.0, le=10.0, description="Maximum IMDb rating"
    ),
    price_min: Optional[float] = Query(None, ge=0.0, description="Minimum price"),
    price_max: Optional[float] = Query(None, ge=0.0, description="Maximum price"),
    db: AsyncSession = Depends(get_db),
) -> MovieListResponseSchema:
    """
    Browse the movie catalog with pagination, filtering, and sorting.

    Behavior:
    - Supports full-text search across title, description, actors, and directors.
    - Supports numeric filtering by year, IMDb rating, and price.
    - Supports sorting by predefined fields.
    - Raises 404 if no movies match filters or if page exceeds total pages.

    Returns:
        MovieListResponseSchema: Paginated list of movies.
    """

    # Validate filter inputs
    if year_min is not None and year_max is not None and year_min > year_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="year_min must be less than or equal to year_max",
        )
    if imdb_min is not None and imdb_max is not None and imdb_min > imdb_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="imdb_min must be less than or equal to imdb_max",
        )
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="price_min must be less than or equal to price_max",
        )

    stmt = select(
        MovieModel,
    ).distinct()

    search_conditions = []
    if title:
        search_conditions.append(MovieModel.name.ilike(f"%{title}%"))
    if description:
        search_conditions.append(MovieModel.description.ilike(f"%{description}%"))
    if actor:
        stmt = stmt.join(MovieStarModel, MovieStarModel.c.movie_id == MovieModel.id)
        stmt = stmt.join(StarModel, StarModel.id == MovieStarModel.c.star_id)
        search_conditions.append(StarModel.name.ilike(f"%{actor}%"))
    if director:
        stmt = stmt.join(
            MovieDirectorModel, MovieDirectorModel.c.movie_id == MovieModel.id
        )
        stmt = stmt.join(
            DirectorModel, DirectorModel.id == MovieDirectorModel.c.director_id
        )
        search_conditions.append(DirectorModel.name.ilike(f"%{director}%"))

    filter_conditions = []
    if genre:
        stmt = stmt.join(MovieGenreModel, MovieGenreModel.c.movie_id == MovieModel.id)
        stmt = stmt.join(GenreModel, GenreModel.id == MovieGenreModel.c.genre_id)
        filter_conditions.append(GenreModel.name.ilike(f"%{genre}%"))
    if year_min is not None:
        filter_conditions.append(MovieModel.year >= year_min)
    if year_max is not None:
        filter_conditions.append(MovieModel.year <= year_max)
    if imdb_min is not None:
        filter_conditions.append(MovieModel.imdb >= imdb_min)
    if imdb_max is not None:
        filter_conditions.append(MovieModel.imdb <= imdb_max)
    if price_min is not None:
        filter_conditions.append(MovieModel.price >= price_min)
    if price_max is not None:
        filter_conditions.append(MovieModel.price <= price_max)

    # Combine conditions with OR (or use and_ for stricter matching)
    conditions = search_conditions + filter_conditions
    if conditions:
        stmt = stmt.where(and_(*conditions))

    # Count total items (filtered)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    print("DEBUG:", stmt.compile(compile_kwargs={"literal_binds": True}))

    total_items = (await db.execute(count_stmt)).scalar_one()

    if total_items == 0:
        raise HTTPException(404, "No movies found.")

    total_pages = (total_items + per_page - 1) // per_page
    offset = (page - 1) * per_page

    if page > total_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page} not found. Total pages available: {total_pages}.",
        )

    # SORTING
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

    print(
        "DEBUG PAGINATED:",
        paginated_stmt.compile(compile_kwargs={"literal_binds": True}),
    )
    result = await db.execute(paginated_stmt)

    movies = result.scalars().all()
    print(f"DEBUG: Returned {len(movies)} movies for page {page}, per_page {per_page}")

    base_url = "/movies/"
    prev_page = next_page = None
    if page > 1:
        prev_page = f"{base_url}?page={page-1}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}"
        if title:
            prev_page += f"&title={title}"
        if description:
            prev_page += f"&description={description}"
        if actor:
            prev_page += f"&actor={actor}"
        if director:
            prev_page += f"&director={director}"

        if year_min is not None:
            prev_page += f"&year_min={year_min}"
        if year_max is not None:
            prev_page += f"&year_max={year_max}"
        if imdb_min is not None:
            prev_page += f"&imdb_min={imdb_min}"
        if imdb_max is not None:
            prev_page += f"&imdb_max={imdb_max}"

    if page < total_pages:
        next_page = f"{base_url}?page={page+1}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}"

        if title:
            next_page += f"&title={title}"
        if description:
            next_page += f"&description={description}"
        if actor:
            next_page += f"&actor={actor}"
        if director:
            next_page += f"&director={director}"

        if year_min is not None:
            next_page += f"&year_min={year_min}"
        if year_max is not None:
            next_page += f"&year_max={year_max}"
        if imdb_min is not None:
            next_page += f"&imdb_min={imdb_min}"
        if imdb_max is not None:
            next_page += f"&imdb_max={imdb_max}"

    return MovieListResponseSchema(
        movies=movies,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.get(
    "/{movie_id}/",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_200_OK,
    summary="Get movie details by ID",
    description=(
        "Returns full details for a specific movie, including genres, "
        "directors, stars, certification, and user interaction metadata."
    ),
    responses={
        200: {
            "description": "Movie retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "name": "Inception",
                        "year": 2010,
                        "imdb": 8.8,
                        "genres": [{"id": 1, "name": "Sci-Fi"}],
                        "directors": [{"id": 1, "name": "Christopher Nolan"}],
                        "stars": [{"id": 1, "name": "Leonardo DiCaprio"}],
                    }
                }
            },
        },
        404: {
            "description": "Movie not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        },
    },
)
async def get_movie_by_id(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
) -> MovieDetailSchema:
    """
    Retrieve detailed information about a movie by its ID.

    Behavior:
    - Loads related entities (genres, directors, stars, certification).
    - Raises 404 if the movie does not exist.

    Args:
        movie_id (int): Movie identifier.
        db (AsyncSession): Database session.

    Returns:
        MovieDetailSchema: Full movie details.
    """
    stmt = (
        select(
            MovieModel,
        )
        .options(
            joinedload(MovieModel.certification),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.stars),
            joinedload(MovieModel.directors),
            joinedload(MovieModel.favorited_by_users),
            joinedload(MovieModel.liked_by_users),
        )
        .where(MovieModel.id == movie_id)
    )

    result = await db.execute(stmt)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    return movie
