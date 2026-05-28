from fastapi import FastAPI
from app.api.auth import router as auth_router

app = FastAPI(title="Task Management API")

app.include_router(auth_router)
