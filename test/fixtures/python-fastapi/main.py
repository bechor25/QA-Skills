from fastapi import FastAPI
from src.auth import router as auth_router
from src.users import router as users_router

app = FastAPI(title="QA-Skills Test Fixture — FastAPI")
app.include_router(auth_router)
app.include_router(users_router)
