from fastapi import FastAPI
from src.storages import create_bucket_if_not_exists
from contextlib import asynccontextmanager
from typing import AsyncGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await create_bucket_if_not_exists()
    print("Bucket ensured. App starting...")
    yield
    print("App shutting down...")
