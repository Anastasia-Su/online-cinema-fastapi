from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, asc, desc
from sqlalchemy.exc import IntegrityError
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
    MovieLikeModel,
    UserFavoriteMovieModel,
    get_db,
)
from src.schemas import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema
from src.schemas.movies import MovieCreateSchema, MovieUpdateSchema
from ..utils import SortBy, SortOrder

from sqlalchemy import select, func, literal_column
from sqlalchemy.orm import contains_eager

fav_count_subq = (
    select(func.count(UserFavoriteMovieModel.c.user_id))
        .where(UserFavoriteMovieModel.c.movie_id == MovieModel.id)
        .scalar_subquery()
)

like_count_subq = (
    select(func.count(MovieLikeModel.c.user_id))
        .where(
        and_(
            MovieLikeModel.c.movie_id == MovieModel.id,
            MovieLikeModel.c.like.is_(True)
        )
    )
        .scalar_subquery()
)




router = APIRouter(prefix="/movies", tags=["movies"])


@router.get(
    "/",
    response_model=MovieListResponseSchema,
    summary="Browse the movie catalog with pagination, filtering, and sorting",
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
):

    # Validate filter inputs
    if year_min is not None and year_max is not None and year_min > year_max:
        raise HTTPException(
            status_code=400, detail="year_min must be less than or equal to year_max"
        )
    if imdb_min is not None and imdb_max is not None and imdb_min > imdb_max:
        raise HTTPException(
            status_code=400, detail="imdb_min must be less than or equal to imdb_max"
        )
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(
            status_code=400, detail="price_min must be less than or equal to price_max"
        )

    # stmt = select(MovieModel).distinct()
    stmt = (
        select(
        MovieModel,
        func.coalesce(fav_count_subq, 0).label("favorite_count"),
        func.coalesce(like_count_subq, 0).label("like_count"),
    )
        .distinct()
    )

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
    summary="Get movie details by ID",
)
async def get_movie_by_id(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
) -> MovieDetailSchema:
    """
    Retrieve detailed information about a specific movie by its ID.
    """
    stmt = (
        select(
            MovieModel,
            func.coalesce(fav_count_subq, 0).label("favorite_count"),
            func.coalesce(like_count_subq, 0).label("like_count"),
            # fav_count_subq.label("favorites_count"),
            # like_count_subq.label("likes_count"),
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
    movie = result.first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )
        
    movie_obj, favorite_count, like_count = movie
    movie_dict = {
        **movie_obj.__dict__,
        "favorite_count": favorite_count,
        "like_count": like_count,
    }

    return MovieDetailSchema.model_validate(movie_dict)
