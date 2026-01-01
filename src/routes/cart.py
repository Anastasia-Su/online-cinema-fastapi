from fastapi import APIRouter, Depends, HTTPException, status, Body, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import select, delete
from src.database import (
    get_db,
    CartModel,
    CartItemModel,
    UserModel,
    MovieModel,
    PaymentModel,
    PaymentItemModel,
    PaymentStatusEnum,
    OrderItemModel,
    OrderModel,
    OrderStatusEnum,
)
from src.config.get_current_user import get_current_user
from src.schemas import CartSchema, CartItemSchema, MovieCartSchema

router = APIRouter(prefix="/cart", tags=["cart"])


async def get_or_create_cart(db: AsyncSession, user_id: int) -> CartModel:
    """
    Retrieve or create a shopping cart for a user.

    If a cart does not exist, a new empty cart is created and persisted.

    :param db: SQLAlchemy async database session.
    :type db: AsyncSession
    :param user_id: ID of the user owning the cart.
    :type user_id: int

    :return: User's shopping cart.
    :rtype: CartModel
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
    status_code=status.HTTP_200_OK,
    summary="Get user cart",
    description="Retrieve the current user's shopping cart. If the cart does not exist, it is created automatically.",
    responses={
        200: {
            "description": "Cart retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {"movie": {"id": 1, "name": "Inception"}, "quantity": 1}
                        ]
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def get_user_cart(
    db: AsyncSession = Depends(get_db), user: UserModel = Depends(get_current_user)
) -> CartModel:
    """
    Get the authenticated user's shopping cart.

    If the user does not already have a cart, an empty cart is created.

    :param db: SQLAlchemy async database session.
    :type db: AsyncSession
    :param user: Current authenticated user.
    :type user: UserModel

    :return: User's shopping cart.
    :rtype: CartModel
    """

    cart = await get_or_create_cart(db, user.id)
    return cart


@router.post(
    "/add",
    status_code=status.HTTP_201_CREATED,
    summary="Add movie to cart",
    description="Add a movie to the authenticated user's shopping cart.",
    responses={
        201: {
            "description": "Movie added to cart",
            "content": {
                "application/json": {"example": {"message": "Movie added to cart"}}
            },
        },
        400: {
            "description": "Movie already in cart or already purchased",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie has already been purchased."}
                }
            },
        },
        404: {
            "description": "Movie not found",
            "content": {
                "application/json": {"example": {"detail": "Movie does not exist."}}
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def add_movie_to_cart(
    movie_id: int = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """
    Add a movie to the user's shopping cart.

    Validation rules:
    - Movie must exist
    - Movie must not already be in the cart
    - Movie must not already be purchased

    Request body example:
        {
            "movie_id": 42
        }

    :param movie_id: ID of the movie to add.
    :type movie_id: int
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession
    :param user: Current authenticated user.
    :type user: UserModel

    :return: Confirmation message.
    :rtype: dict[str, str]

    :raises HTTPException:
        - 404 if the movie does not exist.
        - 400 if the movie is already in the cart or already purchased.
    """

    cart = await get_or_create_cart(db, user.id)

    movie = await db.execute(select(MovieModel).where(MovieModel.id == movie_id))
    if movie.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Movie does not exist."
        )

    # Check if already in cart
    exists = await db.execute(
        select(CartItemModel).where(
            CartItemModel.cart_id == cart.id, CartItemModel.movie_id == movie_id
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Movie is already in the cart.",
        )
    # Check if already purchased
    order_result = await db.execute(
        select(OrderModel)
        .join(OrderItemModel)
        .where(
            OrderModel.user_id == user.id,
            OrderItemModel.movie_id == movie_id,
            OrderModel.status == OrderStatusEnum.PAID,
        )
    )

    order = order_result.scalars().first()

    if order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Movie has already been purchased.",
        )

    # Add new item
    item = CartItemModel(cart_id=cart.id, movie_id=movie_id)
    db.add(item)
    await db.commit()

    return {"message": "Movie added to cart"}


@router.delete(
    "/remove/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove movie from cart",
    description="Remove a movie from the authenticated user's shopping cart.",
    responses={
        204: {"description": "Movie removed from cart"},
        404: {
            "description": "Movie not found in cart",
            "content": {
                "application/json": {"example": {"detail": "Item not in cart."}}
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {"example": {"detail": "Not authenticated"}}
            },
        },
    },
)
async def remove_from_cart(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> Response:
    """
    Remove a movie from the user's shopping cart.

    :param movie_id: ID of the movie to remove.
    :type movie_id: int
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession
    :param user: Current authenticated user.
    :type user: UserModel

    :return: Empty response with HTTP 204 status.
    :rtype: Response

    :raises HTTPException:
        - 404 if the movie is not present in the cart.
    """

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

    return Response(status_code=status.HTTP_204_NO_CONTENT)
