from enum import Enum

from sqlalchemy import delete, insert, update, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models.movies.movies_actions import MovieLikeModel  # adjust path if needed




class SortBy(str, Enum):
    PRICE = "price"
    YEAR = "year"
    IMDB = "imdb"
    VOTES = "votes"
    TIME = "time"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"
    
    

async def toggle_movie_reaction(
    db: AsyncSession,
    user_id: int,
    movie_id: int,
    is_like: bool,
) -> None:
    """
    Like or dislike a movie.
    - If user already liked/disliked → update to new value
    - If user had the opposite reaction → flip it
    - If no reaction exists → insert new one
    """
    # Step 1: Check current reaction (if any)
    current = await db.scalar(
        select(MovieLikeModel.c.like).where(
            MovieLikeModel.c.user_id == user_id,
            MovieLikeModel.c.movie_id == movie_id
        )
    )

    if current is None:
        # No reaction yet → insert
        stmt = insert(MovieLikeModel).values(
            user_id=user_id,
            movie_id=movie_id,
            like=is_like
        )
        await db.execute(stmt)

    elif current != is_like:
        # Opposite reaction exists → update
        stmt = (
            update(MovieLikeModel)
            .where(
                MovieLikeModel.c.user_id == user_id,
                MovieLikeModel.c.movie_id == movie_id
            )
            .values(like=is_like)
        )
        await db.execute(stmt)

    # else:
    #     # Same reaction already exists → remove it (optional!)
    #     # Comment this block if you want "pressing like again" to keep the like
    #     stmt = delete(MovieLikeModel).where(
    #         MovieLikeModel.c.user_id == user_id,
    #         MovieLikeModel.c.movie_id == movie_id
    #     )
    #     await db.execute(stmt)

    await db.commit()