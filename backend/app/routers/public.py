"""The only data shared without signing in: three numbers for the home page."""

import threading
import time

from fastapi import APIRouter

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


def clear() -> None:
    with _lock:
        _cache.clear()
