from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select, update, insert, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.ratings import RatingCreateSchema, RatingSchema
from src.database import MovieRatingModel, MovieModel, get_db, get_current_user, UserModel
from ..utils import update_movie_rating_stats


router = APIRouter(prefix="/movies", tags=["movies"])


@router.post(
    "/{movie_id}/rating",
    response_model=RatingSchema,
    status_code=status.HTTP_201_CREATED,
)
async def rate_movie(
    movie_id: int,
    payload: RatingCreateSchema,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
   
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")


    select_result = await db.execute(
        select(MovieRatingModel.rating).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    current_rating = select_result.scalar_one_or_none()
    
    update_stmt = (
        update(MovieRatingModel)
        .where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
        .values(rating=payload.rating, updated_at=func.now())
      
    )

    result = await db.execute(update_stmt)
    await db.flush()

    rating_obj = result.scalar_one_or_none()  # ← READ ONCE ONLY

    if not rating_obj:
        # INSERT
        insert_stmt = insert(MovieRatingModel).values(
            user_id=current_user.id,
            movie_id=movie_id,
            rating=payload.rating,
        )

        result = await db.execute(insert_stmt)
        await db.flush()
        rating_obj = result.scalar_one()
        
    await update_movie_rating_stats(
        db=db, movie_id=movie_id, old_rating=current_rating, new_rating=payload.rating
    )
    
    await db.commit()

    return RatingSchema(
        user_id=rating_obj.user_id,
        movie_id=rating_obj.movie_id,
        rating=rating_obj.rating,
        created_at=rating_obj.created_at,
        updated_at=rating_obj.updated_at,
        username=current_user.email,
    )


@router.get("/{movie_id}/rating", response_model=RatingSchema)
async def get_my_rating(
    movie_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MovieRatingModel).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You haven't rated this movie yet")

    return RatingSchema(
        user_id=rating.user_id,
        movie_id=rating.movie_id,
        rating=rating.rating,
        created_at=rating.created_at,
        updated_at=rating.updated_at,
        username=current_user.email,
    )


@router.delete("/{movie_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rating(
    movie_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    
    current_rating_result = await db.execute(
        select(MovieRatingModel.rating).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    current_rating = current_rating_result.scalar_one_or_none()

    if current_rating is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You haven't rated this movie")
    
    result = await db.execute(
        delete(MovieRatingModel).where(
            MovieRatingModel.user_id == current_user.id,
            MovieRatingModel.movie_id == movie_id,
        )
    )
    

    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rating not found")

    await update_movie_rating_stats(
            db=db, movie_id=movie_id, old_rating=current_rating, new_rating=None
        )
    
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)