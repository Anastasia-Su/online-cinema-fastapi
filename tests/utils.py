from src.security.token_manager import JWTAuthManager

from sqlalchemy import select

from src.database import UserModel


async def make_token(user, jwt_manager):
    access = jwt_manager.create_access_token({"user_id": user.id})
    return {"Authorization": f"Bearer {access}"}


async def get_headers(db_session, jwt_manager, group_id: int = 1):
    stmt = select(UserModel).where(UserModel.group_id == group_id)

    result = await db_session.execute(stmt)
    user = result.scalars().first()
    assert user, f"No user found"

    headers = await make_token(user, jwt_manager)
    return headers


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        if key in self.store:
            del self.store[key]

    async def keys(self, pattern):
        # Very simple pattern support for "revoked:*"
        if pattern == "revoked:*":
            return [k for k in self.store.keys() if k.startswith("revoked:")]
        return []
