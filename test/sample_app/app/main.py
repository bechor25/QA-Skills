"""FastAPI entrypoint.

Run dev server:
    uvicorn app.main:app --reload --port 8001

The OpenAPI spec is auto-published at /openapi.json — contract-test skill
points there. Templates render minimal HTML for the UI/a11y skills.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routes import api
from app.users import seed_demo_users

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_demo_users()
    yield


app = FastAPI(
    title="Sample QA App",
    version="0.1.0",
    description="Dummy app for exercising QA-Skills end-to-end.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(api)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"app_name": "Sample QA App"})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@app.get("/quote", response_class=HTMLResponse)
def quote_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "quote.html")
