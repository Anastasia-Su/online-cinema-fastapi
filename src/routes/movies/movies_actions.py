from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy import select, func, and_, asc, desc
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
    get_db,
    get_current_user,
)

from src.schemas import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema
from src.schemas.movies import MovieCreateSchema, MovieUpdateSchema
from ..utils import SortBy, SortOrder, toggle_movie_reaction


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post("/{movie_id}/like", status_code=204)
async def like_movie(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await toggle_movie_reaction(db, user.id, movie_id, is_like=True)


@router.post("/{movie_id}/dislike", status_code=204)
async def dislike_movie(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await toggle_movie_reaction(db, user.id, movie_id, is_like=False)


@router.post("/{movie_id}/favorite", status_code=204)
async def add_to_favorites(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fav = UserFavoriteMovieModel(user_id=user.id, movie_id=movie_id)
    db.add(fav)
    await db.commit()


@router.delete("/{movie_id}/favorite", status_code=204)
async def remove_from_favorites(
    movie_id: int,
    _: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(UserFavoriteMovieModel).where(
        UserFavoriteMovieModel.movie_id == movie_id
    )
    result = await db.execute(stmt)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=404, detail="Movie with the given ID was not found."
        )

    await db.delete(movie)
    await db.commit()


@router.get("/favorites", response_model=MovieListResponseSchema)
async def get_favorites(
    user: UserModel = Depends(get_current_user),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    # Reuse ALL the same filters as the main list
    title: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    director: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    sort_by: SortBy = Query(SortBy.IMDB),
    sort_order: SortOrder = Query(SortOrder.DESC),
    year_min: Optional[int] = Query(None, ge=1895),
    year_max: Optional[int] = Query(None, le=2030),
    imdb_min: Optional[float] = Query(None, ge=0.0, le=10.0),
    imdb_max: Optional[float] = Query(None, ge=0.0, le=10.0),
    price_min: Optional[float] = Query(None, ge=0.0),
    price_max: Optional[float] = Query(None, ge=0.0),
    db: AsyncSession = Depends(get_db),
):
    # Start with user's favorites
    stmt = (
        select(MovieModel)
        .join(
            UserFavoriteMovieModel, UserFavoriteMovieModel.c.movie_id == MovieModel.id
        )
        .where(UserFavoriteMovieModel.c.user_id == user.id)
        .distinct()
    )

    # === REUSE EXACT SAME FILTERING LOGIC AS MAIN LIST ===
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
    if genre:
        stmt = stmt.join(MovieGenreModel, MovieGenreModel.c.movie_id == MovieModel.id)
        stmt = stmt.join(GenreModel, GenreModel.id == MovieGenreModel.c.genre_id)
        search_conditions.append(GenreModel.name.ilike(f"%{genre}%"))

    filter_conditions = []
    if year_min:
        filter_conditions.append(MovieModel.year >= year_min)
    if year_max:
        filter_conditions.append(MovieModel.year <= year_max)
    if imdb_min:
        filter_conditions.append(MovieModel.imdb >= imdb_min)
    if imdb_max:
        filter_conditions.append(MovieModel.imdb <= imdb_max)
    if price_min:
        filter_conditions.append(MovieModel.price >= price_min)
    if price_max:
        filter_conditions.append(MovieModel.price <= price_max)

    conditions = search_conditions + filter_conditions
    if conditions:
        stmt = stmt.where(and_(*conditions))

    # === COUNT TOTAL ===
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
            status_code=404, detail=f"Page {page} exceeds total pages ({total_pages})"
        )

    # === SORTING ===
    sort_column = {
        SortBy.PRICE: MovieModel.price,
        SortBy.YEAR: MovieModel.year,
        SortBy.IMDB: MovieModel.imdb,
        SortBy.VOTES: MovieModel.votes,
        SortBy.TIME: MovieModel.time,
    }[sort_by]
    sort_func = asc if sort_order == SortOrder.ASC else desc
    stmt = stmt.order_by(sort_func(sort_column))

    # === PAGINATION ===
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)

    result = await db.execute(stmt)
    movies = result.scalars().all()

    # === BUILD PAGINATION LINKS ===
    base = "/movies/favorites?"
    params = (
        f"page={page}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}"
    )
    prev_page = (
        f"{base}{params.replace(f'page={page}', f'page={page-1}')}"
        if page > 1
        else None
    )
    next_page = (
        f"{base}{params.replace(f'page={page}', f'page={page+1}')}"
        if page < total_pages
        else None
    )

    # Add active filters to prev/next links
    filter_params = []
    for key, val in [
        ("title", title),
        ("description", description),
        ("actor", actor),
        ("director", director),
        ("genre", genre),
        ("year_min", year_min),
        ("year_max", year_max),
        ("imdb_min", imdb_min),
        ("imdb_max", imdb_max),
        ("price_min", price_min),
        ("price_max", price_max),
    ]:
        if val is not None:
            filter_params.append(f"{key}={val}")

    extra = "&" + "&".join(filter_params) if filter_params else ""
    if prev_page:
        prev_page += extra
    if next_page:
        next_page += extra

    return MovieListResponseSchema(
        movies=[MovieListItemSchema.from_orm(m) for m in movies],
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )
