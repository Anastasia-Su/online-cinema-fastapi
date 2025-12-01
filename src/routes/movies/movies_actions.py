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
    get_current_user,
)

from src.schemas import MovieListResponseSchema, MovieListItemSchema, MovieDetailSchema
from src.schemas.movies import MovieCreateSchema, MovieUpdateSchema
from ..utils import SortBy, SortOrder, toggle_movie_reaction, increment_counter


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post("/{movie_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def like_movie(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await toggle_movie_reaction(db, user.id, movie_id, is_like=True)


@router.post("/{movie_id}/dislike", status_code=status.HTTP_204_NO_CONTENT)
async def dislike_movie(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await toggle_movie_reaction(db, user.id, movie_id, is_like=False)


@router.delete("/{movie_id}/reaction", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reaction(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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


@router.post("/{movie_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_favorites(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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


@router.delete("/{movie_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_favorites(
    movie_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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


@router.get("/favorites", response_model=MovieListResponseSchema)
async def get_favorites(
    user: UserModel = Depends(get_current_user),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    title: Optional[str] = Query(None, description="Search by movie title"),
    db: AsyncSession = Depends(get_db),
):

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
