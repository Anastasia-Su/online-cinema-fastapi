import os
import secrets

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from src.storages.lifespan import lifespan


from src.routes import (
    movie_base_router,
    movie_action_router,
    genre_router,
    accounts_router,
    profiles_router,
    admin_router,
    moderator_router,
    comments_router,
    ratings_router,
    cart_router,
    order_router,
    payment_router,
)


security = HTTPBasic()

def swagger_auth(credentials: HTTPBasicCredentials = Depends(security)):
    print("=== SWAGGER_AUTH CALLED ===")
    print(f"Username from client: '{credentials.username}'")
    print(f"Password from client: '{credentials.password}'")

    user = os.getenv("SWAGGER_USER")
    password = os.getenv("SWAGGER_PASSWORD")

    print(f"Expected user: '{user}'")
    print(f"Expected password: {'*' * len(password) if password else None}")

    if not user or not password:
        print("WARNING: SWAGGER_USER or SWAGGER_PASSWORD not set - allowing access")
        return  

    if not (
        secrets.compare_digest(credentials.username, user)
        and secrets.compare_digest(credentials.password, password)
    ):
        print("AUTH FAILED - RAISING 401")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": 'Basic realm="Swagger UI"'},
        )

    print("AUTH SUCCESS")
    return credentials


# app = FastAPI(
#     title="Movies",
#     description="Description of project",
#     lifespan=lifespan,
#     swagger_ui_parameters={
#         "persistAuthorization": True,
#     },
# )

app = FastAPI(
    title="Movies",
    description=(
        "Online movie store that supports movie browsing, ratings, likes, favorites, "
        "carts, orders, payments, authentication, and role-based access control."
    ),
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,
    },
    docs_url=None,       
    redoc_url=None,       
    openapi_url=None,   
)

# 🔐 Protected Swagger
@app.get("/docs", include_in_schema=False)
def custom_swagger_ui(auth=Depends(swagger_auth)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Movies API",
    )


@app.get("/openapi.json", include_in_schema=False)
def openapi(auth=Depends(swagger_auth)):
    return get_openapi(
        title="Movies",
        version="1.0.0",
        routes=app.routes,
    )



app.include_router(admin_router)
app.include_router(accounts_router)
app.include_router(profiles_router)
app.include_router(movie_base_router)
app.include_router(movie_action_router)
app.include_router(comments_router)
app.include_router(ratings_router)
app.include_router(genre_router)
app.include_router(admin_router)
app.include_router(moderator_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(payment_router)

print("SWAGGER_USER:", os.getenv("SWAGGER_USER"))
print("SWAGGER_PASSWORD:", os.getenv("SWAGGER_PASSWORD"))
