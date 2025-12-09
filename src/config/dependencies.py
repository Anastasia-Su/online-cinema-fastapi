import os

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import TestingSettings, Settings, BaseAppSettings

# from src.database import get_db, UserModel
from src.config.get_settings import get_settings
from src.notifications import EmailSenderInterface, EmailSender
from src.security.interfaces import JWTAuthManagerInterface
from src.security.token_manager import JWTAuthManager
from src.storages import S3StorageInterface, S3StorageClient
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.tasks.redis_blacklist import get_redis, is_token_revoked
from src.exceptions import TokenExpiredError, InvalidTokenError


bearer_scheme = HTTPBearer(auto_error=False)


def get_jwt_auth_manager(
    settings: BaseAppSettings = Depends(get_settings),
) -> JWTAuthManagerInterface:
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM,
    )


def get_accounts_email_notificator(
    settings: BaseAppSettings = Depends(get_settings),
) -> EmailSenderInterface:

    return EmailSender(
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        email=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        template_dir=settings.PATH_TO_EMAIL_TEMPLATES_DIR,
        activation_email_template_name=settings.ACTIVATION_EMAIL_TEMPLATE_NAME,
        activation_complete_email_template_name=settings.ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME,
        password_email_template_name=settings.PASSWORD_RESET_TEMPLATE_NAME,
        password_complete_email_template_name=settings.PASSWORD_RESET_COMPLETE_TEMPLATE_NAME,
        comment_reply_template_name=settings.COMMENT_REPLY_TEMPLATE_NAME,
    )


def get_s3_storage_client(
    settings: BaseAppSettings = Depends(get_settings),
) -> S3StorageInterface:

    return S3StorageClient(
        endpoint_url=settings.S3_STORAGE_ENDPOINT,
        access_key=settings.S3_STORAGE_ACCESS_KEY,
        secret_key=settings.S3_STORAGE_SECRET_KEY,
        bucket_name=settings.S3_BUCKET_NAME,
    )
