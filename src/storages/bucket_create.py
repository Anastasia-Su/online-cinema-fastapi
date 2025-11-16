from fastapi import FastAPI, Depends
from src.config import get_settings
from src.config.settings import TestingSettings, Settings, BaseAppSettings
import aioboto3


async def create_bucket_if_not_exists(
    settings: BaseAppSettings = get_settings(),
):
    session = aioboto3.Session(
        aws_access_key_id=settings.S3_STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.S3_STORAGE_SECRET_KEY,
    )
    async with session.client(
        "s3", endpoint_url=settings.S3_STORAGE_ENDPOINT
    ) as client:
        try:
            await client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            print(f"Bucket '{settings.S3_BUCKET_NAME}' exists.")
        except client.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                await client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
                print(f"Bucket '{settings.S3_BUCKET_NAME}' created.")
            else:
                raise
