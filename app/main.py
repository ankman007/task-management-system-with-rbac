from fastapi import FastAPI
from app.api.auth import router as auth_router
from app.api.task import router as task_router
from app.api.role import router as role_router
from app.core import swagger

app = FastAPI(
    title=swagger.TITLE,
    version=swagger.VERSION,
    description=swagger.DESCRIPTION,
    openapi_tags=swagger.TAGS_METADATA,
    docs_url=None
)

app.include_router(auth_router)
app.include_router(task_router)
app.include_router(role_router)

swagger.configure_swagger(app)
