from fastapi import FastAPI

app = FastAPI()

from app.api.auth import router as auth_router
app.include_router(auth_router)

from app.api.task import router as task_router
app.include_router(task_router)
