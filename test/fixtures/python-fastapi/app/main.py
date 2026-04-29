from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from app.routes import auth, users
from app.database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="QA Fixture — Python FastAPI")
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])

templates = Jinja2Templates(directory="app/templates")


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")
