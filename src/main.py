from fastapi import FastAPI

from src.routes import (
    movie_router,
    genre_router, 
    accounts_router
)
#     accounts_router,
#     profiles_router
# )

app = FastAPI(
    title="Movies",
    description="Description of project"
)

# api_version_prefix = "/api/v1"

app.include_router(accounts_router)
# app.include_router(profiles_router, prefix=f"{api_version_prefix}/profiles", tags=["profiles"])
app.include_router(movie_router, )
app.include_router(genre_router)
