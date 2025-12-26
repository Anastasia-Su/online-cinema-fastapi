import asyncio
from datetime import datetime, timezone, timedelta
import aioredis
from typing import cast

from fastapi import APIRouter, Depends, status, HTTPException, Response, Query, Form
from pydantic import EmailStr
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.config import (
    get_jwt_auth_manager,
    # get_settings,
    BaseAppSettings,
    get_accounts_email_notificator,
    # get_current_user,
)
from src.config.get_settings import get_settings
from src.database import (
    get_db,
    # get_current_user,
    UserGroupModel,
    UserGroupEnum,
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserModel,
)
from src.config.get_current_user import get_current_user

from src.exceptions import BaseSecurityError
from src.notifications import EmailSenderInterface
from src.schemas import (
    UserRegistrationRequestSchema,
    UserRegistrationResponseSchema,
    MessageResponseSchema,
    UserActivationRequestSchema,
    PasswordResetRequestSchema,
    PasswordResetCompleteRequestSchema,
    ChangePasswordRequestSchema,
    UserLoginResponseSchema,
    UserLoginRequestSchema,
    TokenRefreshRequestSchema,
    TokenRefreshResponseSchema,
)
from src.security.interfaces import JWTAuthManagerInterface

from src.tasks.redis_blacklist import (
    revoke_token,
    is_token_revoked,
    list_revoked_tokens,
    get_redis,
)
from fastapi.security import OAuth2PasswordBearer

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/accounts/login/")
bearer_scheme = HTTPBearer(auto_error=False)


router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
    "/register/",
    response_model=UserRegistrationResponseSchema,
    summary="User Registration",
    description="Register a new user with an email and password.",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "User registered successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "email": "test@example.com",
                        "is_active": False,
                        "group": "USER",
                    }
                }
            },
        },
        409: {
            "description": "Conflict - User with this email already exists.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "A user with this email test@example.com already exists."
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred during user creation.",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred during user creation."}
                }
            },
        },
    },
)
async def register_user(
    user_data: UserRegistrationRequestSchema,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> UserRegistrationResponseSchema:
    """
    Endpoint for user registration.

    Registers a new user, hashes their password, and assigns them to the default user group.
    If a user with the same email already exists, an HTTP 409 error is raised.
    In case of any unexpected issues during the creation process, an HTTP 500 error is returned.

    Args:
        user_data (UserRegistrationRequestSchema): The registration details including email and password.
        db (AsyncSession): The asynchronous database session.
        email_sender (EmailSenderInterface): The asynchronous email sender.

    Returns:
        UserRegistrationResponseSchema: The newly created user's details.

    Raises:
        HTTPException:
            - 409 Conflict if a user with the same email exists.
            - 500 Internal Server Error if an error occurs during user creation.
    """
    stmt = select(UserModel).where(UserModel.email == user_data.email)
    result = await db.execute(stmt)
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with this email {user_data.email} already exists.",
        )

    stmt = select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.USER)
    result = await db.execute(stmt)
    user_group = result.scalars().first()
    if not user_group:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user group not found.",
        )

    try:
        new_user = UserModel.create(
            email=str(user_data.email),
            raw_password=user_data.password,
            group_id=user_group.id,
        )
        db.add(new_user)
        await db.flush()

        activation_token = ActivationTokenModel(user_id=new_user.id)
        db.add(activation_token)

        await db.commit()
        await db.refresh(new_user)
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during user creation.",
        ) from e
    else:
        activation_link = f"http://127.0.0.1/accounts/activate/?email={new_user.email}&token={activation_token.token}"

        await email_sender.send_activation_email(new_user.email, activation_link)

        return UserRegistrationResponseSchema.model_validate(new_user)


@router.post(
    "/activate/resend/",
    response_model=MessageResponseSchema,
    summary="Resend account activation email",
    description=(
        "Resends the account activation email if the user exists and is not yet active. "
        "Always returns a generic success response to prevent user enumeration."
    ),
    responses={
        200: {
            "description": "Activation email sent if applicable",
            "content": {
                "application/json": {
                    "examples": {
                        "user_not_registered": {
                            "summary": "User does not exist",
                            "value": {"message": "This user is not registered."},
                        },
                        "already_active": {
                            "summary": "User already active",
                            "value": {"message": "This user is already active."},
                        },
                        "email_sent": {
                            "summary": "Activation email sent",
                            "value": {
                                "message": "You will receive an email with instructions."
                            },
                        },
                    }
                }
            },
        },
    },
)
async def resend_activation(
    request: PasswordResetRequestSchema,  # reuse simple schema with `email` field
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    """
    Resend account activation email.

    If a user with the provided email exists and is not yet activated,
    a new activation token is generated and an activation email is sent.
    Any previously issued activation tokens for this user are invalidated.

    To prevent user enumeration, this endpoint always returns a generic
    success message regardless of whether the user exists or is already active.

    Args:
        request (PasswordResetRequestSchema): Request containing the user's email.
        db (AsyncSession): The asynchronous database session.
        email_sender (EmailSenderInterface): Service responsible for sending emails.

    Returns:
        MessageResponseSchema: A generic response message indicating that
        instructions will be sent if applicable.
    """

    stmt = select(UserModel).filter_by(email=request.email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    # always return same message to avoid user enumeration
    if not user:
        return MessageResponseSchema(message="This user is not registered.")

    # If user is already active — nothing to resend
    if user.is_active:
        return MessageResponseSchema(message="This user is already active.")

    # Delete old activation token(s) and create new one
    await db.execute(
        delete(ActivationTokenModel).where(ActivationTokenModel.user_id == user.id)
    )
    new_token = ActivationTokenModel(user_id=user.id)
    db.add(new_token)
    await db.commit()
    activation_link = f"http://127.0.0.1:8000/accounts/activate/?email={user.email}&token={new_token.token}"
    await email_sender.send_activation_email(user.email, activation_link)
    return MessageResponseSchema(message="You will receive an email with instructions.")


@router.get(
    "/activate/",
    response_model=MessageResponseSchema,
    summary="Activate user account via email link",
    description="Validates activation token from URL and activates the user.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Account activated successfully",
            "content": {
                "application/json": {
                    "example": {"message": "Account activated. Please log in."}
                }
            },
        },
        400: {
            "description": "Invalid, expired, or already used token",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_token": {
                            "summary": "Invalid or expired token",
                            "value": {"detail": "Invalid or expired activation token."},
                        },
                        "already_active": {
                            "summary": "Account already active",
                            "value": {"detail": "User account is already active."},
                        },
                    }
                }
            },
        },
    },
)
async def activate_account(
    email: EmailStr = Query(...),
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    """
    Activate a user account using an email verification token.

    Validates the activation token associated with the given email.
    If the token is valid and not expired, the user's account is activated
    and the activation token is deleted.

    If the token is invalid, expired, or the account is already active,
    an appropriate HTTP 400 error is returned.

    Args:
        email (EmailStr): The user's email address.
        token (str): Activation token received via email.
        db (AsyncSession): The asynchronous database session.
        email_sender (EmailSenderInterface): Service responsible for sending emails.

    Returns:
        MessageResponseSchema: Confirmation message indicating successful activation.

    Raises:
        HTTPException:
            - 400 Bad Request if the token is invalid, expired, or already used.
    """

    stmt = (
        select(ActivationTokenModel)
        .options(joinedload(ActivationTokenModel.user))
        .join(UserModel)
        .where(UserModel.email == email, ActivationTokenModel.token == token)
    )
    result = await db.execute(stmt)
    token_record = result.scalars().first()

    if not token_record or token_record.expires_at.replace(
        tzinfo=timezone.utc
    ) < datetime.now(timezone.utc):
        if token_record:
            await db.delete(token_record)
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired activation token.",
        )

    user = token_record.user
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is already active.",
        )

    user.is_active = True
    await db.delete(token_record)
    await db.commit()

    login_link = "http://127.0.0.1/accounts/login/"
    await email_sender.send_activation_complete_email(email, login_link)

    return MessageResponseSchema(message="Account activated. Please log in.")


@router.post(
    "/logout",
    summary="Logout current user",
    description=(
        "Logs out the currently authenticated user by revoking the active access token "
        "and deleting all associated refresh tokens. "
        "The revoked access token is stored in Redis until expiration."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {
            "description": "User logged out successfully",
        },
        401: {
            "description": "Unauthorized - Access token is missing or invalid",
            "content": {"application/json": {"example": {"detail": "Unauthorized"}}},
        },
        400: {
            "description": "Logout failed due to token revocation error",
            "content": {"application/json": {"example": {"detail": "Logout failed"}}},
        },
    },
)
async def logout_user(
    _=Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    """
    Log out the currently authenticated user.

    Revokes the active access token by adding it to a Redis-based blacklist
    until its expiration time. All refresh tokens associated with the user
    are also deleted from the database.

    This ensures that both access and refresh tokens can no longer be used
    after logout.

    Args:
        credentials (HTTPAuthorizationCredentials | None): Bearer access token.
        jwt_manager (JWTAuthManagerInterface): JWT authentication manager.
        db (AsyncSession): The asynchronous database session.
        redis (aioredis.Redis): Redis connection used for token revocation.

    Returns:
        Response: HTTP 204 No Content on successful logout.

    Raises:
        HTTPException:
            - 401 Unauthorized if the token is missing or invalid.
            - 400 Bad Request if token revocation fails.
    """

    if credentials:
        token = credentials.credentials
    try:
        payload = jwt_manager.decode_access_token(token)

        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    user_id = payload.get("user_id")
    await db.execute(
        delete(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id)
    )
    await db.commit()

    try:
        await revoke_token(token, expires_at, redis)
        revoked_tokens = await list_revoked_tokens()
        print("revoked_tokens_list", revoked_tokens)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Logout failed"
        )


@router.post(
    "/change-password/",
    response_model=MessageResponseSchema,
    summary="Change user password",
    description=(
        "Allows an authenticated user to change their password. "
        "The current password must be provided for verification."
    ),
    responses={
        200: {
            "description": "Password updated successfully",
            "content": {
                "application/json": {
                    "example": {"message": "Password updated successfully."}
                }
            },
        },
        400: {
            "description": "Old password is incorrect",
            "content": {
                "application/json": {
                    "example": {"detail": "Old password is incorrect."}
                }
            },
        },
        401: {
            "description": "Unauthorized - User is not authenticated",
            "content": {"application/json": {"example": {"detail": "Unauthorized"}}},
        },
    },
)
async def change_password(
    data: ChangePasswordRequestSchema,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponseSchema:
    """
    Change the password of the currently authenticated user.

    Verifies the provided current password before updating it
    with the new password. The operation is allowed only for
    authenticated users.

    Args:
        data (ChangePasswordRequestSchema): Contains the old and new passwords.
        user (UserModel): The currently authenticated user.
        db (AsyncSession): The asynchronous database session.

    Returns:
        MessageResponseSchema: Confirmation message indicating successful password update.

    Raises:
        HTTPException:
            - 400 Bad Request if the old password is incorrect.
            - 401 Unauthorized if the user is not authenticated.
    """

    if not user.verify_password(data.old_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect.",
        )

    user.password = data.new_password
    await db.commit()
    return MessageResponseSchema(message="Password updated successfully.")


@router.post(
    "/password-reset/request/",
    response_model=MessageResponseSchema,
    summary="Request Password Reset Token",
    description=(
        "Allows a user to request a password reset token. If the user exists and is active, "
        "a new token will be generated and any existing tokens will be invalidated."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Password reset instructions sent if user exists",
            "content": {
                "application/json": {
                    "example": {
                        "message": "If you are registered, you will receive an email with instructions."
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - Failed to generate token",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to generate password reset token."}
                }
            },
        },
    },
)
async def request_password_reset_token(
    data: PasswordResetRequestSchema,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    """
    Endpoint to request a password reset token.

    If the user exists and is active, invalidates any existing password reset tokens and generates a new one.
    Always responds with a success message to avoid leaking user information.

    Args:
        data (PasswordResetRequestSchema): The request data containing the user's email.
        db (AsyncSession): The asynchronous database session.
        email_sender (EmailSenderInterface): The asynchronous email sender.

    Returns:
        MessageResponseSchema: A success message indicating that instructions will be sent.
    """
    stmt = select(UserModel).filter_by(email=data.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.is_active:
        return MessageResponseSchema(message="A user does not exist or not active.")

    await db.execute(
        delete(PasswordResetTokenModel).where(
            PasswordResetTokenModel.user_id == user.id
        )
    )

    reset_token = PasswordResetTokenModel(user_id=cast(int, user.id))
    db.add(reset_token)
    await db.commit()

    password_reset_complete_link = f"http://127.0.0.1/accounts/password-reset-complete/?token={reset_token.token}&email={data.email}"

    await email_sender.send_password_reset_email(
        str(data.email), password_reset_complete_link
    )

    return MessageResponseSchema(
        message="If you are registered, you will receive an email with instructions."
    )


@router.post(
    "/reset-password/complete/",
    response_model=MessageResponseSchema,
    summary="Reset User Password",
    description="Reset a user's password if a valid token is provided.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Password reset successfully",
            "content": {
                "application/json": {
                    "example": {"message": "Password reset successfully."}
                }
            },
        },
        400: {
            "description": (
                "Bad Request - The provided email or token is invalid, "
                "the token has expired, or the user account is not active."
            ),
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_email_or_token": {
                            "summary": "Invalid Email or Token",
                            "value": {"detail": "Invalid email or token."},
                        },
                        "expired_token": {
                            "summary": "Expired Token",
                            "value": {"detail": "Invalid email or token."},
                        },
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred while resetting the password.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while resetting the password."
                    }
                }
            },
        },
    },
)
async def reset_password(
    token: str = Form(...),
    password: str = Form(...),
    email: EmailStr = Form(...),
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSenderInterface = Depends(get_accounts_email_notificator),
) -> MessageResponseSchema:
    """
    Endpoint for resetting a user's password.

    Validates the token and updates the user's password if the token is valid and not expired.
    Deletes the token after a successful password reset.

    Args:
        data (PasswordResetCompleteRequestSchema): The request data containing the user's email,
         token, and new password.
        db (AsyncSession): The asynchronous database session.
        email_sender (EmailSenderInterface): The asynchronous email sender.

    Returns:
        MessageResponseSchema: A response message indicating successful password reset.

    Raises:
        HTTPException:
            - status.HTTP_400_BAD_REQUEST Bad Request if the email or token is invalid, or the token has expired.
            - 500 Internal Server Error if an error occurs during the password reset process.
    """
    stmt = select(UserModel).filter_by(email=email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or token.",
        )

    stmt = select(PasswordResetTokenModel).filter_by(user_id=user.id)
    result = await db.execute(stmt)
    token_record = result.scalars().first()

    if not token_record or token_record.token != token:
        if token_record:
            await db.run_sync(lambda s: s.delete(token_record))
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or token.",
        )

    expires_at = cast(datetime, token_record.expires_at).replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.run_sync(lambda s: s.delete(token_record))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or token.",
        )

    try:
        user.password = password
        await db.run_sync(lambda s: s.delete(token_record))
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting the password.",
        )

    login_link = "http://127.0.0.1/accounts/login/"

    await email_sender.send_password_reset_complete_email(str(email), login_link)

    return MessageResponseSchema(message="Password reset successfully.")


@router.post(
    "/login/",
    response_model=UserLoginResponseSchema,
    summary="User Login",
    description="Authenticate a user and return access and refresh tokens.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized - Invalid email or password.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid email or password."}
                }
            },
        },
        403: {
            "description": "Forbidden - User account is not activated.",
            "content": {
                "application/json": {
                    "example": {"detail": "User account is not activated."}
                }
            },
        },
        500: {
            "description": "Internal Server Error - An error occurred while processing the request.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while processing the request."
                    }
                }
            },
        },
    },
)
async def login_user(
    login_data: UserLoginRequestSchema,
    db: AsyncSession = Depends(get_db),
    settings: BaseAppSettings = Depends(get_settings),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> UserLoginResponseSchema:
    """
    Endpoint for user login.

    Authenticates a user using their email and password.
    If authentication is successful, creates a new refresh token and returns both access and refresh tokens.

    Args:
        login_data (UserLoginRequestSchema): The login credentials.
        db (AsyncSession): The asynchronous database session.
        settings (BaseAppSettings): The application settings.
        jwt_manager (JWTAuthManagerInterface): The JWT authentication manager.

    Returns:
        UserLoginResponseSchema: A response containing the access and refresh tokens.

    Raises:
        HTTPException:
            - 401 Unauthorized if the email or password is invalid.
            - 403 Forbidden if the user account is not activated.
            - 500 Internal Server Error if an error occurs during token creation.
    """
    stmt = select(UserModel).filter_by(email=login_data.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.verify_password(login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not activated.",
        )

    jwt_refresh_token = jwt_manager.create_refresh_token({"user_id": user.id})

    try:
        await db.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.user_id == user.id)
        )

        refresh_token = RefreshTokenModel.create(
            user_id=user.id,
            days_valid=settings.LOGIN_TIME_DAYS,
            token=jwt_refresh_token,
        )
        db.add(refresh_token)
        await db.flush()
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request.",
        )

    jwt_access_token = jwt_manager.create_access_token({"user_id": user.id})
    return UserLoginResponseSchema(
        access_token=jwt_access_token,
        refresh_token=jwt_refresh_token,
    )


@router.post(
    "/refresh/",
    response_model=TokenRefreshResponseSchema,
    summary="Refresh Access Token",
    description="Refresh the access token using a valid refresh token.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "New access token issued successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                    }
                }
            },
        },
        400: {
            "description": "Bad Request - The provided refresh token is invalid or expired.",
            "content": {
                "application/json": {"example": {"detail": "Token has expired."}}
            },
        },
        401: {
            "description": "Unauthorized - Refresh token not found.",
            "content": {
                "application/json": {"example": {"detail": "Refresh token not found."}}
            },
        },
        404: {
            "description": "Not Found - The user associated with the token does not exist.",
            "content": {"application/json": {"example": {"detail": "User not found."}}},
        },
    },
)
async def refresh_access_token(
    token_data: TokenRefreshRequestSchema,
    db: AsyncSession = Depends(get_db),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> TokenRefreshResponseSchema:
    """
    Endpoint to refresh an access token.

    Validates the provided refresh token, extracts the user ID from it, and issues
    a new access token. If the token is invalid or expired, an error is returned.

    Args:
        token_data (TokenRefreshRequestSchema): Contains the refresh token.
        db (AsyncSession): The asynchronous database session.
        jwt_manager (JWTAuthManagerInterface): JWT authentication manager.

    Returns:
        TokenRefreshResponseSchema: A new access token.

    Raises:
        HTTPException:
            - status.HTTP_400_BAD_REQUEST Bad Request if the token is invalid or expired.
            - 401 Unauthorized if the refresh token is not found.
            - 404 Not Found if the user associated with the token does not exist.
    """
    try:
        decoded_token = jwt_manager.decode_refresh_token(token_data.refresh_token)
        user_id = decoded_token.get("user_id")
    except BaseSecurityError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    stmt = select(RefreshTokenModel).filter_by(token=token_data.refresh_token)
    result = await db.execute(stmt)
    refresh_token_record = result.scalars().first()
    if not refresh_token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )

    stmt = select(UserModel).filter_by(id=user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    new_access_token = jwt_manager.create_access_token({"user_id": user_id})

    return TokenRefreshResponseSchema(access_token=new_access_token)
