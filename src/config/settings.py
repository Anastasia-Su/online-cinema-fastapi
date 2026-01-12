import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv

load_dotenv()


class BaseAppSettings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent
    PATH_TO_DB: str = str(BASE_DIR / "database" / "source" / "cinema_sqlite.db")
    # PATH_TO_MOVIES_CSV: str = str(BASE_DIR / "database" / "seed_data" / "imdb_movies.csv")

    PATH_TO_EMAIL_TEMPLATES_DIR: str = str(BASE_DIR / "notifications" / "templates")
    ACTIVATION_EMAIL_TEMPLATE_NAME: str = "activation_request.html"
    ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME: str = "activation_complete.html"
    PASSWORD_RESET_TEMPLATE_NAME: str = "password_reset_request.html"
    PASSWORD_RESET_COMPLETE_TEMPLATE_NAME: str = "password_reset_complete.html"
    COMMENT_REPLY_TEMPLATE_NAME: str = "comment_reply.html"
    COMMENT_LIKE_TEMPLATE_NAME: str = "comment_like.html"
    PAYMENT_EMAIL_TEMPLATE_NAME: str = "payment.html"
    LOGIN_TIME_DAYS: int = 7

    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "host")
    EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", 1025))
    EMAIL_HOST_USER: str = os.getenv("EMAIL_HOST_USER", "testuser")
    EMAIL_HOST_PASSWORD: str = os.getenv("EMAIL_HOST_PASSWORD", "test_password")
    EMAIL_USE_TLS: bool = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"
    MAILHOG_API_PORT: int = os.getenv("MAILHOG_API_PORT", 8025)

    S3_STORAGE_HOST: str = os.getenv("MINIO_HOST", "minio")
    S3_STORAGE_PORT: int = os.getenv("MINIO_PORT", 9000)
    S3_STORAGE_ACCESS_KEY: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    S3_STORAGE_SECRET_KEY: str = os.getenv("MINIO_ROOT_PASSWORD", "some_password")
    S3_BUCKET_NAME: str = os.getenv("MINIO_STORAGE", "movies-storage")

    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
    )

    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET")

    @property
    def S3_STORAGE_ENDPOINT(self) -> str:
        return f"http://{self.S3_STORAGE_HOST}:{self.S3_STORAGE_PORT}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseAppSettings):
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "test_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "test_password")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "test_host")
    POSTGRES_DB_PORT: int = int(os.getenv("POSTGRES_DB_PORT", 5432))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "test_db")

    SECRET_KEY_ACCESS: str = os.getenv("SECRET_KEY_ACCESS", os.urandom(32))
    SECRET_KEY_REFRESH: str = os.getenv("SECRET_KEY_REFRESH", os.urandom(32))
    JWT_SIGNING_ALGORITHM: str = os.getenv("JWT_SIGNING_ALGORITHM", "HS256")


class TestingSettings(BaseAppSettings):
    PATH_TO_DB: str = ":memory:"

    SECRET_KEY_ACCESS: str = "SECRET_KEY_ACCESS"
    SECRET_KEY_REFRESH: str = "SECRET_KEY_REFRESH"
    JWT_SIGNING_ALGORITHM: str = "HS256"

    STRIPE_SECRET_KEY: str = "STRIPE_SECRET_KEY"
    STRIPE_WEBHOOK_SECRET: str = "STRIPE_WEBHOOK_SECRET"
