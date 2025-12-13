from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import select, delete
from src.database import get_db, CartModel, CartItemModel, UserModel, MovieModel
from src.config.get_current_user import get_current_user
from src.schemas import CartSchema, CartItemSchema, MovieCartSchema

router = APIRouter(prefix="/cart", tags=["cart"])


async def get_or_create_cart(db: AsyncSession, user_id: int) -> CartModel:
    """
    Retrieve the user's cart. If none exists, create a new one.
    """
    result = await db.execute(
        select(CartModel)
        .options(
        selectinload(CartModel.items)
            .selectinload(CartItemModel.movie)
            .selectinload(MovieModel.genres) 
        )
        .where(CartModel.user_id == user_id)
    )
    cart = result.unique().scalar_one_or_none()

    if not cart:
        cart = CartModel(user_id=user_id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
   
    return cart


@router.get(
    "/",
    response_model=CartSchema,
    summary="Get User Cart",
    description="Retrieve the current user's shopping cart. If the cart does not exist, it is automatically created.",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthorized - User is not logged in."},
        500: {"description": "Internal Server Error - Could not retrieve the cart."},
    },
)
async def get_user_cart(
    db: AsyncSession = Depends(get_db), user: UserModel = Depends(get_current_user)
) -> CartModel:
    cart = await get_or_create_cart(db, user.id)
    return cart


@router.post(
    "/add",
    description="Add a movie to the current user's shopping cart.",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Movie already in cart."},
        404: {"description": "Movie not found."},
        401: {"description": "Unauthorized - User is not logged in."},
    },
)
async def add_movie_to_cart(
    movie_id: int = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    cart = await get_or_create_cart(db, user.id)

    movie = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    if movie.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie does not exist."
        )

    # Check if movie already purchased
    # purchased = await db.execute(
    #     select(MovieModel)
    #     .join(UserPurchasedMovie)
    #     .where(
    #         UserPurchasedMovie.user_id == user.id,
    #         UserPurchasedMovie.movie_id == data.movie_id,
    #     )
    # )
    # if purchased.scalar_one_or_none():
    #     raise HTTPException(status_code=400, detail="Movie already purchased.")

    # Check if already in cart
    exists = await db.execute(
        select(CartItemModel)
        
        .where(
            CartItemModel.cart_id == cart.id, CartItemModel.movie_id == movie_id
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Movie is already in the cart.",
        )

    # Add new item
    item = CartItemModel(cart_id=cart.id, movie_id=movie_id)
    db.add(item)
    await db.commit()
    return {"message": "Movie added to cart"}


@router.delete(
    "/remove/{movie_id}",
    summary="Remove Movie from Cart",
    description="Remove a movie from the current user's shopping cart.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Movie not found in cart."},
        401: {"description": "Unauthorized - User is not logged in."},
    },
)
async def remove_from_cart(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> None:
    cart = await get_or_create_cart(db, user.id)

    result = await db.execute(
        delete(CartItemModel).where(
            CartItemModel.cart_id == cart.id, CartItemModel.movie_id == movie_id
        )
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not in cart."
        )

    await db.commit()
