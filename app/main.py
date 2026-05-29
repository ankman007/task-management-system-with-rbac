from fastapi import FastAPI
from app.api.auth import router as auth_router
from app.api.task import router as task_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(task_router)
