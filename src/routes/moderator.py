from fastapi import APIRouter, Depends, HTTPException, status, Path
from typing import Annotated
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
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


@router.get("/users", response_model=list[UserListSchema])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_moderator_or_admin),
):
    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group))
        .order_by(UserModel.id.desc())
    )

    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserDetailSchema)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(require_moderator_or_admin),
):
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
        "<h3>This endpoint allows moderator or admin to add a new movie to the database. "
        "It accepts details such as name, date, genres, actors, languages, and "
        "other attributes. The associated country, genres, actors, and languages "
        "will be created or linked automatically.</h3>"
    ),
    responses={
        201: {
            "description": "Movie created successfully.",
        },
        400: {
            "description": "Invalid input.",
            "content": {
                "application/json": {"example": {"detail": "Invalid input data."}}
            },
        },
    },
    status_code=201,
)
async def post_movie(
    movie_data: MovieCreateSchema,
    _: UserModel = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
) -> MovieDetailSchema:
    """
    Add a new movie to the database.

    This endpoint allows the creation of a new movie with details such as
    name, release date, genres, actors, and languages. It automatically
    handles linking or creating related entities.

    :param movie_data: The data required to create a new movie.
    :type movie_data: MovieCreateSchema
    :param db: The SQLAlchemy async database session (provided via dependency injection).
    :type db: AsyncSession

    :return: The created movie with all details.
    :rtype: MovieDetailSchema

    :raises HTTPException:
        - 409 if a movie with the same name and date already exists.
        - 400 if input data is invalid (e.g., violating a constraint).
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
    description=(
        "<h3>Delete a specific movie from the database by its unique ID.</h3>"
        "<p>If the movie exists, it will be deleted. If it does not exist, "
        "a 404 error will be returned.</p>"
    ),
    responses={
        204: {"description": "Movie deleted successfully."},
        404: {
            "description": "Movie not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie with the given ID was not found."}
                }
            },
        },
    },
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_movie(
    movie_id: int = Path(..., ge=1, le=9_223_372_036_854_775_807),
    _: UserModel = Depends(require_moderator_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a specific movie by its ID.

    This function deletes a movie identified by its unique ID.
    If the movie does not exist, a 404 error is raised.

    :param movie_id: The unique identifier of the movie to delete.
    :type movie_id: int
    :param db: The SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :raises HTTPException: Raises a 404 error if the movie with the given ID is not found.

    :return: A response indicating the successful deletion of the movie.
    :rtype: None
    """

    stmt = select(MovieModel).where(MovieModel.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found.",
        )

    await db.delete(movie)
    await db.commit()


@router.patch(
    "/movies/{movie_id}/",
    summary="Update a movie by ID",
    description=(
        "<h3>Update details of a specific movie by its unique ID.</h3>"
        "<p>This endpoint updates the details of an existing movie. If the movie with "
        "the given ID does not exist, a 404 error is returned.</p>"
    ),
    responses={
        200: {
            "description": "Movie updated successfully.",
            "content": {
                "application/json": {
                    "example": {"detail": "Movie updated successfully."}
                }
            },
        },
        404: {
            "description": "Movie not found.",
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
):
    """
    Update a specific movie by its ID.

    This function updates a movie identified by its unique ID.
    If the movie does not exist, a 404 error is raised.

    :param movie_id: The unique identifier of the movie to update.
    :type movie_id: int
    :param movie_data: The updated data for the movie.
    :type movie_data: MovieUpdateSchema
    :param db: The SQLAlchemy database session (provided via dependency injection).
    :type db: AsyncSession

    :raises HTTPException: Raises a 404 error if the movie with the given ID is not found.

    :return: A response indicating the successful update of the movie.
    :rtype: None
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
