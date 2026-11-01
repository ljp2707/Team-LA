"""The FastAPI app: middleware, API routes, and the built frontend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from app.airtable.client import warn_about_schema_problems
from app.config import get_settings
from app.routers import (
    archive,
    auth,
    health,
    me,
    projects,
    tasks,
    templates,
    users,
)

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION_DAYS = 7

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.is_production:
        warn_about_schema_problems()
    yield


app = FastAPI(title="NMU Launches", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie="nmu_session",
    max_age=SESSION_DAYS * 24 * 60 * 60,
    same_site="lax",
    https_only=settings.is_production,
)

for module in (auth, me, health, projects, tasks, templates, users, archive):
    app.include_router(module.router)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Serve built frontend files, and index.html so React Router works on refresh."""
    if path == "api" or path.startswith(("api/", "auth/")):
        raise HTTPException(404, "Not found")

    file = (STATIC_DIR / path).resolve()
    if path and file.is_file() and file.is_relative_to(STATIC_DIR):
        return FileResponse(file)

    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "Frontend is not built. In development, use port 5173.")
    return FileResponse(index)
