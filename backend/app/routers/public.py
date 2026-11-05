"""The only data shared without signing in: three numbers for the home page, and who runs the app."""

import threading
import time

from fastapi import APIRouter

from app.config import get_settings
from app.services.projects import season_stats
from app.services.views import World

router = APIRouter(prefix="/api/public", tags=["public"])

CACHE_SECONDS = 5 * 60
_lock = threading.Lock()
_cache: dict = {}


@router.get("/season-stats")
def get_season_stats():
    with _lock:
        if _cache and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
    value = season_stats(World())
    with _lock:
        _cache.update(at=time.monotonic(), value=value)
    return value


@router.get("/about")
def about():
    """Who runs NMU Launches and how to reach them, for the Privacy and Terms pages."""
    settings = get_settings()
    return {
        "org_name": settings.ORG_NAME,
        "contact_email": settings.CONTACT_EMAIL or None,
        "address": settings.ORG_ADDRESS or None,
        "app_url": settings.FRONTEND_URL,
    }


def clear() -> None:
    with _lock:
        _cache.clear()
