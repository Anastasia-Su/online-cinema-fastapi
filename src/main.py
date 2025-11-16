from fastapi import FastAPI
from src.storages import create_bucket_if_not_exists
from contextlib import asynccontextmanager

from src.routes import (
    movie_router,
    genre_router, 
    accounts_router,
    profiles_router
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create bucket
    await create_bucket_if_not_exists()
    print("Bucket ensured. App starting...")
    yield
    # Shutdown: (optional cleanup)
    print("App shutting down...")
    
app = FastAPI(
    title="Movies",
    description="Description of project",
    lifespan=lifespan
    
)

# api_version_prefix = "/api/v1"

app.include_router(accounts_router)
app.include_router(profiles_router)
app.include_router(movie_router, )
app.include_router(genre_router)


