import os
import redis.asyncio as redis

# Read our container instance from Docker config
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

# Global client instance
redis_client: redis.Redis | None = None


async def init_redis() -> None:
    """Initializes a shared, persistent Redis connection pool."""
    global redis_client
    redis_client = redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,  # Safeguards connection pool exhaustion
    )


async def close_redis() -> None:
    """Gracefully releases connections during server shutdown."""
    global redis_client
    if redis_client:
        await redis_client.aclose()


def get_redis():
    """Dependency injection provider for your API routers."""
    return redis_client
