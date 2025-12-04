from fastapi import FastAPI
from src.storages import create_bucket_if_not_exists
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_bucket_if_not_exists()
    print("Bucket ensured. App starting...")
    yield
    print("App shutting down...")
