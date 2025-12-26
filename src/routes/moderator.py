from fastapi import APIRouter, Depends, HTTPException, status, Path, Response
from typing import Annotated
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_
from sqlalchemy.orm import joinedload, selectinload
from src.database import (
    UserModel,
    UserGroupModel,
    UserGroupEnum,
    MovieModel,
    CertificationModel,
    StarModel,
    DirectorModel,
    GenreModel,
    CartModel,
    CartItemModel,
    OrderItemModel,
    PaymentModel,
    PaymentItemModel,
    PaymentStatusEnum,
    get_db,
    # get_current_user,
)
from src.config.get_current_user import get_current_user

from src.schemas import (
    UserListSchema,
    UserDetailSchema,
    UserGroupUpdateSchema,
    UserActivateSchema,
    MovieCreateSchema,
    MovieDetailSchema,
    MovieUpdateSchema,
)

from src.config.get_admin import require_moderator_or_admin
from .utils import resolve_relations


router = APIRouter(prefix="/moderator", tags=["moderator"])


@router.get(
    "/users/",
    response_model=list[UserListSchema],
    summary="List all users",
    description=(
        "Returns a list of all registered users. "
        "Accessible only to moderators and administrators."
    ),
    responses={
        200: {
            "description": "Users retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": 1,
                            "email": "user@example.com",
                            "is_active": True,
                            "group": {"id": 2, "name": "USER"},
                        }
                    ]
                }
            },
        },
        403: {
            "description": "Forbidden – insufficient permissions",
            "content": {
                "application/json": {"example": {"detail": "Not enough permissions"}}
            },
        },
    },
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_moderator_or_admin),
) -> list[UserListSchema]:
    """
    Retrieve a list of all users.

    This endpoint returns basic information for every registered user.
    Access is restricted to moderators and administrators.

    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: List of users.
    :rtype: list[UserListSchema]

    :raises HTTPException:
        - 403 if the requesting user lacks sufficient permissions.
    """

    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group))
        .order_by(UserModel.id.desc())
    )

    return result.scalars().all()


@router.get(
    "/users/{user_id}",
    response_model=UserDetailSchema,
    summary="Get user details",
    description="Retrieve detailed information about a specific user by ID.",
    responses={
        200: {
            "description": "User retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "email": "user@example.com",
                        "is_active": True,
                        "group": {"id": 2, "name": "USER"},
                    }
                }
            },
        },
        404: {
            "description": "User not found",
            "content": {"application/json": {"example": {"detail": "User not found"}}},
        },
    },
)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_moderator_or_admin),
) -> UserDetailSchema:
    """
    Retrieve user details by ID.

    This endpoint returns full information about a specific user,
    including their group and activation status.

    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: Detailed user information.
    :rtype: UserDetailSchema

    :raises HTTPException:
        - 404 if the user does not exist.
        - 403 if the requester lacks sufficient permissions.
    """

    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group))
        .where(UserModel.id == user_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.post(
    "/movies/",
    response_model=MovieDetailSchema,
    summary="Add a new movie",
    description=(
        "Creates a new movie entry. "
        "All related entities (genres, stars, directors) must already exist."
    ),
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "Movie created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 10,
                        "name": "Inception",
                        "year": 2010,
                        "genres": [{"id": 1, "name": "Sci-Fi"}],
                        "stars": [{"id": 5, "name": "Leonardo DiCaprio"}],
                        "directors": [{"id": 2, "name": "Christopher Nolan"}],
                    }
                }
            },
        },
        400: {
            "description": "Invalid input data",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_certification": {
                            "summary": "Invalid certification ID",
                            "value": {"detail": "Invalid certification_id"},
                        },
                        "missing_genres": {
                            "summary": "Genres not found",
                            "value": {"detail": "Genres not found: {'Drama'}"},
                        },
                    }
                }
            },
        },
        409: {
            "description": "Movie already exists",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "A movie with the same name and year already exists."
                    }
                }
            },
        },
    },
)
async def post_movie(
    movie_data: MovieCreateSchema,
    _: UserModel = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
) -> MovieDetailSchema:
    """
    Create a new movie.

    This endpoint allows moderators or administrators to add a new movie.
    Related entities (genres, stars, directors) are linked automatically.

    :param movie_data: Data required to create a movie.
    :type movie_data: MovieCreateSchema
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: Newly created movie.
    :rtype: MovieDetailSchema

    :raises HTTPException:
        - 400 if input data is invalid or relations are missing.
        - 409 if a movie with the same name and year already exists.
        - 403 if the requester lacks sufficient permissions.
    """

    existing_stmt = select(MovieModel).where(
        (MovieModel.name == movie_data.name), (MovieModel.year == movie_data.year)
    )
    existing_result = await db.execute(existing_stmt)
    existing_movie = existing_result.scalars().first()

    if existing_movie:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A movie with the name '{movie_data.name}' and release year "
                f"'{movie_data.year}' already exists."
            ),
        )

    certification = await db.scalar(
        select(CertificationModel).where(
            CertificationModel.id == movie_data.certification_id
        )
    )
    if not certification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid certification_id"
        )

    genres = await db.scalars(
        select(GenreModel).where(GenreModel.name.in_(movie_data.genres))
    )
    genres = genres.all()  # materializes

    missing_genres = set(movie_data.genres) - {g.name for g in genres}
    if missing_genres:
        # Optional: auto-create missing genres?
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Genres not found: {missing_genres}",
        )

    stars = await db.scalars(
        select(StarModel).where(StarModel.name.in_(movie_data.stars))
    )
    stars = stars.all()

    directors = await db.scalars(
        select(DirectorModel).where(DirectorModel.name.in_(movie_data.directors))
    )
    directors = directors.all()

    movie_dict = movie_data.model_dump(exclude={"genres", "stars", "directors"})
    movie = MovieModel(
        **movie_dict,
        certification=certification,
        genres=genres,
        stars=stars,
        directors=directors,
    )

    try:
        db.add(movie)
        await db.commit()
        await db.refresh(movie, ["genres", "stars", "directors"])

        return MovieDetailSchema.model_validate(movie)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data."
        )


@router.delete(
    "/movies/{movie_id}/",
    summary="Delete a movie by ID",
    description="Deletes a movie if it is not used in carts or orders.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {
            "description": "Movie deleted successfully",
        },
        404: {
            "description": "Movie not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        },
        409: {
            "description": "Movie cannot be deleted",
            "content": {
                "application/json": {
                    "examples": {
                        "in_cart": {
                            "summary": "Movie in cart",
                            "value": {
                                "detail": "Can't delete. This movie is in user's cart."
                            },
                        },
                        "used_in_orders": {
                            "summary": "Movie used in orders",
                            "value": {
                                "detail": "Can't delete. This movie has been purchased or ordered by users."
                            },
                        },
                    }
                }
            },
        },
    },
)
async def delete_movie(
    movie_id: int = Path(..., ge=1, le=9_223_372_036_854_775_807),
    _: UserModel = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Delete a movie by ID.

    A movie can only be deleted if it is not present in any cart
    and has not been purchased or ordered by users.

    :param movie_id: Unique identifier of the movie.
    :type movie_id: int
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: None
    :rtype: None

    :raises HTTPException:
        - 404 if the movie does not exist.
        - 409 if the movie is used in carts or orders.
        - 403 if the requester lacks sufficient permissions.
    """

    stmt = select(MovieModel).where(MovieModel.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    cart_stmt = select(CartItemModel).where(CartItemModel.movie_id == movie_id).limit(1)

    cart_exists = (await db.execute(cart_stmt)).first()

    if cart_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Can't delete. This movie is in user's cart.",
        )

    order_item_stmt = (
        select(OrderItemModel.id).where(OrderItemModel.movie_id == movie_id).limit(1)
    )

    used_in_orders = (await db.execute(order_item_stmt)).first()

    if used_in_orders:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Can't delete. This movie has been purchased or ordered by users.",
        )

    await db.delete(movie)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/movies/{movie_id}/",
    summary="Update a movie by ID",
    description="Updates movie fields and related entities.",
    responses={
        200: {
            "description": "Movie updated successfully",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie updated successfully."}
                }
            },
        },
        400: {
            "description": "Invalid input data",
            "content": {
                "application/json": {"example": {"detail": "Invalid input data."}}
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
async def update_movie(
    movie_data: MovieUpdateSchema,
    movie_id: int = Path(..., ge=1, le=9_223_372_036_854_775_807),
    _: UserModel = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Update an existing movie.

    This endpoint updates one or more fields of a movie, including
    relational fields such as genres, stars, and directors.

    :param movie_id: Unique identifier of the movie.
    :type movie_id: int
    :param movie_data: Fields to update.
    :type movie_data: MovieUpdateSchema
    :param db: SQLAlchemy async database session.
    :type db: AsyncSession

    :return: Confirmation message.
    :rtype: dict[str, str]

    :raises HTTPException:
        - 400 if provided data is invalid.
        - 404 if the movie does not exist.
        - 403 if the requester lacks sufficient permissions.
    """

    stmt = (
        select(MovieModel)
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
    update_data = movie_data.model_dump(exclude_unset=True)

    RELATION_MAP = {
        "genres": GenreModel,
        "stars": StarModel,
        "directors": DirectorModel,
        "favorited_by_users": UserModel,
        "liked_by_users": UserModel,
    }

    for field, value in update_data.items():
        if field in RELATION_MAP:
            if not isinstance(value, list):
                raise HTTPException(400, f"{field} must be a list of names")
            related_objs = await resolve_relations(db, RELATION_MAP[field], value)
            setattr(movie, field, related_objs)
        else:
            setattr(movie, field, value)

    try:
        await db.commit()
        await db.refresh(movie)
    except IntegrityError as e:
        print(str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data."
        )

    return {"detail": "Movie updated successfully."}
