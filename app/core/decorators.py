import asyncio
import json
from functools import wraps
from fastapi.encoders import jsonable_encoder

def cache_response(ttl_seconds: int = 300, prefix: str = "api_cache"):
    """
    Advanced decorator that caches both sync and async FastAPI endpoints into Redis.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 💡 FIX: Import dynamically inside the wrapper function execution context
            # This guarantees we fetch the active pool *after* lifespan has populated it.
            from app.core import redis
            active_client = redis.redis_client

            if not active_client:
                return func(*args, **kwargs)

            # Clean parameter mapping for unique cache keys
            param_string = ",".join(f"{k}={v}" for k, v in kwargs.items() if k not in ["db", "current_user"])
            cache_key = f"{prefix}:{func.__name__}:{param_string}"

            async def get_cached():
                return await active_client.get(cache_key)

            async def set_cached(value):
                serializable_value = jsonable_encoder(value)
                await active_client.set(name=cache_key, value=json.dumps(serializable_value), ex=ttl_seconds)

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Check Cache Hit
            cached_data = loop.run_until_complete(get_cached())
            if cached_data:
                return json.loads(cached_data)

            # Cache Miss: Execute actual database retrieval
            response_data = func(*args, **kwargs)

            # Save fresh data to Redis safely
            loop.run_until_complete(set_cached(response_data))

            return response_data
        return wrapper
    return decorator