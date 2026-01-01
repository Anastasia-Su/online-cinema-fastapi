from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_s3_storage_client, get_jwt_auth_manager
from src.database import get_db
from src.database.models.accounts import (
    UserModel,
    UserProfileModel,
    GenderEnum,
    UserGroupModel,
    UserGroupEnum,
)
from src.exceptions import BaseSecurityError, S3FileUploadError
from src.schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from src.security.interfaces import JWTAuthManagerInterface
from src.security.http import get_current_user_token
from src.storages import S3StorageInterface

# from fastapi.security import HTTPBearer
# bearer_scheme = HTTPBearer(auto_error=False)


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    summary="Create user profile",
    status_code=status.HTTP_201_CREATED,
    description=(
        "Creates a user profile for a given user ID. "
        "The endpoint handles authentication, checks if a profile already exists, "
        "uploads the avatar to S3, and stores the profile data in the database."
    ),
    responses={
        201: {
            "description": "Profile created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "user_id": 42,
                        "first_name": "John",
                        "last_name": "Doe",
                        "gender": "male",
                        "date_of_birth": "1990-01-01",
                        "info": "Some info about the user",
                        "avatar": "https://s3.example.com/avatars/42_avatar.png",
                    }
                }
            },
        },
        400: {
            "description": "User already has a profile",
            "content": {
                "application/json": {
                    "example": {"detail": "User already has a profile."}
                }
            },
        },
        401: {
            "description": "Unauthorized: user not found, inactive, or invalid token",
            "content": {
                "application/json": {
                    "example": {"detail": "User not found or not active."}
                }
            },
        },
        403: {
            "description": "Forbidden: user does not have permission to create/edit this profile",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "You don't have permission to edit this profile."
                    }
                }
            },
        },
        500: {
            "description": "Failed to upload avatar",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to upload avatar. Please try again later."
                    }
                }
            },
        },
    },
)
async def create_profile(
    user_id: int,
    # token: str = Depends(get_token),
    token: str = Depends(get_current_user_token),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
    profile_data: ProfileCreateSchema = Depends(ProfileCreateSchema.from_form),
) -> ProfileResponseSchema:
    """
    Create a user profile for the specified user.

    Steps:
    1. Validate user authentication token.
    2. Check if the user has permission to create/edit this profile.
    3. Ensure the user exists and is active.
    4. Verify the user does not already have a profile.
    5. Upload avatar image to S3 storage.
    6. Create and store the profile in the database.
    7. Return the created profile details with avatar URL.

    :param user_id: The ID of the user for whom the profile is being created.
    :type user_id: int
    :param token: Authentication token for the current user.
    :type token: str
    :param jwt_manager: JWT manager for decoding and validating tokens.
    :type jwt_manager: JWTAuthManagerInterface
    :param db: Async SQLAlchemy session.
    :type db: AsyncSession
    :param s3_client: S3 storage client for avatar upload.
    :type s3_client: S3StorageInterface
    :param profile_data: Profile data from a multipart/form-data request.
    :type profile_data: ProfileCreateSchema

    :return: Created profile details including avatar URL.
    :rtype: ProfileResponseSchema

    :raises HTTPException:
        - 400 if the user already has a profile.
        - 401 if the user is not found, inactive, or token is invalid.
        - 403 if the current user does not have permission to create/edit the profile.
        - 500 if the avatar upload to S3 fails.
    """

    try:
        payload = jwt_manager.decode_access_token(token)
        token_user_id = payload.get("user_id")
    except BaseSecurityError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    if user_id != token_user_id:
        stmt = (
            select(UserGroupModel).join(UserModel).where(UserModel.id == token_user_id)
        )
        result = await db.execute(stmt)
        user_group = result.scalars().first()
        if not user_group or user_group.name == UserGroupEnum.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this profile.",
            )

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    stmt_profile = select(UserProfileModel).where(UserProfileModel.user_id == user.id)
    result_profile = await db.execute(stmt_profile)
    existing_profile = result_profile.scalars().first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    avatar_bytes = await profile_data.avatar.read()
    avatar_key = f"avatars/{user.id}_{profile_data.avatar.filename}"

    try:
        await s3_client.upload_file(file_name=avatar_key, file_data=avatar_bytes)
    except S3FileUploadError as e:
        print(f"Error uploading avatar to S3: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later.",
        )

    new_profile = UserProfileModel(
        user_id=cast(int, user.id),
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=cast(GenderEnum, profile_data.gender),
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key,
    )

    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    avatar_url = await s3_client.get_file_url(new_profile.avatar)

    return ProfileResponseSchema(
        id=new_profile.id,
        user_id=new_profile.user_id,
        first_name=new_profile.first_name,
        last_name=new_profile.last_name,
        gender=new_profile.gender,
        date_of_birth=new_profile.date_of_birth,
        info=new_profile.info,
        avatar=cast(HttpUrl, avatar_url),
    )
