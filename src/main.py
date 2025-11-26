from fastapi import FastAPI, Request
from src.storages import create_bucket_if_not_exists
from contextlib import asynccontextmanager
from fastapi.openapi.docs import get_swagger_ui_html

# from fastapi_swagger_dark import dark_swagger_theme
from src.storages.lifespan import lifespan

from src.routes import (
    movie_base_router,
    movie_action_router,
    genre_router,
    accounts_router,
    profiles_router,
    admin_router,
    comments_router,
)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await create_bucket_if_not_exists()
#     print("Bucket ensured. App starting...")
#     yield
#     print("App shutting down...")


app = FastAPI(
    title="Movies",
    description="Description of project",
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,
    },
)


app.include_router(admin_router)
app.include_router(accounts_router)
app.include_router(profiles_router)
app.include_router(movie_base_router)
app.include_router(movie_action_router)
app.include_router(comments_router)
app.include_router(genre_router)
app.include_router(admin_router)
