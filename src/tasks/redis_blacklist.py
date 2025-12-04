# src/redis.py
from fastapi import Depends
import aioredis
from datetime import datetime, timezone

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get shared Redis connection (lazy init)."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            "redis://localhost:6379",  # "redis://localhost:6379"
            decode_responses=True,
            encoding="utf-8",
        )
        # Optional: test connection
        try:
            await _redis.ping()
        except aioredis.ConnectionError:
            raise RuntimeError("Cannot connect to Redis. Is Docker running?")
    return _redis


async def revoke_token(token: str, expires_at: datetime, redis: aioredis.Redis):
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    ttl = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    if ttl <= 0:
        return

    try:
        await redis.set(f"revoked:{token}", "1", ex=ttl)
    except aioredis.ConnectionError:
        # Log, but don't crash
        pass


async def is_token_revoked(token: str, redis: aioredis.Redis) -> bool:
    """
    Check if token is blacklisted.
    """
    try:
        return await redis.get(f"revoked:{token}") is not None
    except aioredis.RedisError:
        # Fail open? Or fail closed?
        # For security: assume NOT revoked if Redis down
        return False


# ——— Admin / Debug Only ———
# WARNING: KEYS is slow! Use only in dev or admin endpoint
async def list_revoked_tokens(redis: aioredis.Redis = Depends(get_redis)):
    """For debugging only. Never use in production route."""
    try:
        keys = await redis.keys("revoked:*")
        return [key.split(":", 1)[1] for key in keys]
    except aioredis.RedisError as e:
        print(f"Redis error in list_revoked_tokens: {e}")
        return []
