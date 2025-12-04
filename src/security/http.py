from fastapi import Request, HTTPException, status, Depends


# src/security/http.py
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import HTTPException, status

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
        )
    return credentials.credentials


# def get_token(request: Request) -> str:
#     """
#     Extracts the Bearer token from the Authorization header.

#     :param request: FastAPI Request object.
#     :return: Extracted token string.
#     :raises HTTPException: If Authorization header is missing or invalid.
#     """


#     authorization: str = request.headers.get("Authorization")

#     if not authorization:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authorization header is missing"
#         )

#     scheme, _, token = authorization.partition(" ")

#     if scheme.lower() != "bearer" or not token:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid Authorization header format. Expected 'Bearer <token>'"
#         )

#     return token
