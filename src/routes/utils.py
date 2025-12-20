from enum import Enum
from fastapi import HTTPException

from sqlalchemy import delete, insert, update, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    # get_async_session,
    MovieModel,
    MovieLikeModel,
    UserFavoriteMovieModel,
    MovieCommentModel,
    MovieRatingModel,
    CartModel,
    CartItemModel,
    MovieModel,
    OrderItemModel,
    PaymentStatusEnum,
    PaymentModel,
    PaymentItemModel,
)


from sqlalchemy.orm import selectinload


class SortBy(str, Enum):
    PRICE = "price"
    YEAR = "year"
    IMDB = "imdb"
    VOTES = "votes"
    TIME = "time"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


async def increment_counter(
    db: AsyncSession, movie_id: int, counter: str, delta: int = 1
):
    await db.execute(
        update(MovieModel)
        .where(MovieModel.id == movie_id)
        .values(**{counter: MovieModel.__table__.c[counter] + delta})
    )


async def toggle_movie_reaction(
    db: AsyncSession,
    user_id: int,
    movie_id: int,
    is_like: bool,
) -> None:
    # 1. Get current reaction (if any)
    current = await db.scalar(
        select(MovieLikeModel.c.like).where(
            MovieLikeModel.c.user_id == user_id, MovieLikeModel.c.movie_id == movie_id
        )
    )

    delta = 0

    if current is None:
        # No reaction → new one
        if is_like:
            delta = +1
        # if dislike → delta stays 0 (we don't count dislikes)

        await db.execute(
            insert(MovieLikeModel).values(
                user_id=user_id, movie_id=movie_id, like=is_like
            )
        )

    elif current != is_like:
        # Switching reaction
        if current is True and not is_like:
            delta = -1  # Was like → now dislike → remove from count
        elif not current and is_like:
            delta = +1  # Was dislike → now like → add to count

        await db.execute(
            update(MovieLikeModel)
            .where(
                MovieLikeModel.c.user_id == user_id,
                MovieLikeModel.c.movie_id == movie_id,
            )
            .values(like=is_like)
        )
    else:
        # Same reaction again → do nothing (or you could remove it — up to you)
        return

    # 2. Only update counter if it actually affects like_count
    if delta != 0:
        await increment_counter(db, movie_id, "like_count", delta)

    await db.commit()


async def backfill_all_counters(db: AsyncSession):

    print("Starting backfill using pure SQLAlchemy...")

    # 1. Reset all counters to 0 (safety)
    await db.execute(
        update(MovieModel).values(
            like_count=0,
            favorite_count=0,
            comment_count=0,
            rating_count=0,
            rating_average=0.0,
        )
    )

    # 2. Re-count everything using SQLAlchemy only
    movies = await db.execute(select(MovieModel.id))
    movie_ids = [row[0] for row in movies.fetchall()]

    for movie_id in movie_ids:
        # Like count
        like_cnt = await db.scalar(
            select(func.count())
            .select_from(MovieLikeModel)
            .where(
                MovieLikeModel.c.movie_id == movie_id, MovieLikeModel.c.like.is_(True)
            )
        )

        # Favorite count
        fav_cnt = await db.scalar(
            select(func.count())
            .select_from(UserFavoriteMovieModel)
            .where(UserFavoriteMovieModel.c.movie_id == movie_id)
        )

        # Comment count
        comment_cnt = await db.scalar(
            select(func.count())
            .select_from(MovieCommentModel)
            .where(MovieCommentModel.movie_id == movie_id)
        )

        # Rating count + average
        rating_stats = await db.execute(
            select(func.count(), func.avg(MovieRatingModel.rating)).where(
                MovieRatingModel.movie_id == movie_id
            )
        )
        rating_count, rating_avg = rating_stats.first()
        rating_count = rating_count or 0
        rating_avg = round(float(rating_avg or 0.0), 2)

        # Update movie with correct values
        await db.execute(
            update(MovieModel)
            .where(MovieModel.id == movie_id)
            .values(
                like_count=like_cnt or 0,
                favorite_count=fav_cnt or 0,
                comment_count=comment_cnt or 0,
                rating_count=rating_count,
                rating_average=rating_avg,
            )
        )

    await db.commit()
    print(f"Backfilled {len(movie_ids)} movies using pure SQLAlchemy!")


async def update_movie_rating_stats(
    db: AsyncSession, movie_id: int, old_rating: float | None, new_rating: float | None
):
    """
    Call this after any rating change.
    old_rating = previous value (None if insert)
    new_rating = new value (None if delete)
    """

    movie = await db.get(MovieModel, movie_id)
    if not movie:
        return
    current_avg = movie.rating_average or 0.0
    current_count = movie.rating_count or 0

    if old_rating is None and new_rating is not None:
        # INSERT
        new_count = current_count + 1
        new_avg = (current_avg * current_count + new_rating) / new_count
    elif old_rating is not None and new_rating is not None:
        # UPDATE
        new_count = current_count
        new_avg = (current_avg * current_count - old_rating + new_rating) / new_count
    elif old_rating is not None and new_rating is None:
        # DELETE
        if current_count <= 1:
            new_avg = 0.0
            new_count = 0
        else:
            new_count = current_count - 1
            new_avg = (current_avg * current_count - old_rating) / new_count
    else:
        return  # no change

    movie.rating_average = round(new_avg, 2)
    movie.rating_count = new_count
    # await db.commit()


async def resolve_relations(db, model_cls, names: list[str]):
    """
    Resolve a list of names to ORM objects.
    - Case-insensitive matching (Postgres-friendly)
    - Trims whitespace
    - Raises HTTPException listing exactly which names were not found
    - Returns ORM objects in the same order as the input list
    """
    if not names:
        return []

    # Trim and casefold inputs
    names_cleaned = [n.strip() for n in names]
    names_lowered = [n.casefold() for n in names_cleaned]

    # Query DB
    q = select(model_cls).where(func.lower(model_cls.name).in_(names_lowered))
    res = await db.execute(q)
    objs = res.scalars().all()

    # Map found names
    found_lowered = {o.name.casefold(): o for o in objs}

    # Detect missing
    missing = [
        orig
        for orig, low in zip(names_cleaned, names_lowered)
        if low not in found_lowered
    ]
    if missing:
        raise HTTPException(
            400, detail=f"Unknown {model_cls.__name__} names: {', '.join(missing)}"
        )

    # Return objects in same order as input
    return [found_lowered[low] for low in names_lowered]


async def delete_paid_items_for_user(
    db: AsyncSession,
    user_id: int,
):
    cart = (
        await db.execute(select(CartModel).where(CartModel.user_id == user_id))
    ).scalar_one_or_none()

    if not cart:
        return 0

    paid_movie_ids_subq = (
        select(OrderItemModel.movie_id)
        .join(PaymentItemModel, PaymentItemModel.order_item_id == OrderItemModel.id)
        .join(PaymentModel, PaymentModel.id == PaymentItemModel.payment_id)
        .where(
            PaymentModel.status == PaymentStatusEnum.SUCCESSFUL,
            PaymentModel.user_id == user_id,
        )
    )

    await db.execute(
        delete(CartItemModel).where(
            CartItemModel.cart_id == cart.id,
            CartItemModel.movie_id.in_(paid_movie_ids_subq),
        )
    )

    # return result.rowcount or 0
