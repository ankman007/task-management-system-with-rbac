from fastapi import FastAPI
from app.api.auth import router as auth_router
from app.api.task import router as task_router
from app.api.role import router as role_router
from app.api.user import router as user_router
from app.core import swagger
from contextlib import asynccontextmanager
from app.core.redis import init_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    print("Redis connection pool ready.")
    yield
    await close_redis()
    print("Redis connection pool closed safely.")


app = FastAPI(
    title=swagger.TITLE,
    version=swagger.VERSION,
    description=swagger.DESCRIPTION,
    openapi_tags=swagger.TAGS_METADATA,
    lifespan=lifespan,
    docs_url=None,
)

app.include_router(auth_router)
app.include_router(task_router)
app.include_router(role_router)
app.include_router(user_router)

swagger.configure_swagger(app)
