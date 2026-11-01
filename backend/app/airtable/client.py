"""The only code that talks to Airtable.

Airtable allows 5 requests per second per base, and locks a base out for 30 seconds
if that limit is passed. So reads are cached for 30 seconds, requests are spaced
out, and pyairtable retries with backoff if Airtable still answers 429.

The token stays here on the server. Never send it to the browser or log it.
"""

import logging
import threading
import time
from functools import lru_cache
from typing import Any

from pyairtable import Api, retry_strategy

from app.airtable.schema import ALL_TABLES, field_names
from app.config import get_settings

logger = logging.getLogger(__name__)

CACHE_SECONDS = 30
SECONDS_BETWEEN_REQUESTS = 0.25  # 4 per second, just under Airtable's limit

_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = threading.Lock()
_rate_lock = threading.Lock()
_next_request_at = 0.0


@lru_cache
def get_api() -> Api:
    return Api(
        get_settings().AIRTABLE_TOKEN,
        retry_strategy=retry_strategy(total=5, backoff_factor=1),
    )


def get_base():
    return get_api().base(get_settings().AIRTABLE_BASE_ID)


def is_configured() -> bool:
    """False until real Airtable values have been put in the environment."""
    settings = get_settings()
    return bool(settings.AIRTABLE_BASE_ID) and settings.AIRTABLE_TOKEN not in (
        "",
        "pat_replace_me",
    )


def _wait_for_turn() -> None:
    """Sleep just long enough to keep requests under the rate limit."""
    global _next_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = _next_request_at - now
        _next_request_at = max(now, _next_request_at) + SECONDS_BETWEEN_REQUESTS
    if wait > 0:
        time.sleep(wait)


def all_records(table_name: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
    """Return every record in a table, from the cache if it is fresh enough."""
    key = (table_name, tuple(fields or ()))
    with _cache_lock:
        cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    records: list[dict[str, Any]] = []
    _wait_for_turn()
    # Each page is one Airtable request, so wait again before fetching the next.
    for page in get_base().table(table_name).iterate(fields=fields or []):
        records.extend(page)
        _wait_for_turn()

    with _cache_lock:
        _cache[key] = (time.monotonic(), records)
    return records


def clear_cache() -> None:
    """Forget cached reads. Call this after any write to Airtable."""
    with _cache_lock:
        _cache.clear()


def table_counts() -> list[dict[str, Any]]:
    """Return the record count for each table, or an error for that table."""
    results = []
    for table in ALL_TABLES:
        try:
            # Ask for one field only, since just the number of records is needed.
            first_field = field_names(table)[0]
            count = len(all_records(table.TABLE, [first_field]))
            results.append({"table": table.TABLE, "count": count, "error": None})
        except Exception as error:
            # Only the error type: messages can include request details.
            logger.warning("Could not read %s: %s", table.TABLE, type(error).__name__)
            results.append(
                {"table": table.TABLE, "count": None, "error": type(error).__name__}
            )
    return results


def find_schema_problems() -> list[str]:
    """Compare schema.py to the real base and describe anything missing."""
    tables = {table.name: table for table in get_base().schema().tables}
    problems = []
    for table in ALL_TABLES:
        real_table = tables.get(table.TABLE)
        if real_table is None:
            problems.append(f"Table missing: {table.TABLE}")
            continue
        real_fields = {field.name for field in real_table.fields}
        for name in field_names(table):
            if name not in real_fields:
                problems.append(f"Field missing: {table.TABLE} > {name}")
    return problems


def warn_about_schema_problems() -> None:
    """Log a warning per mismatch. Never stops the app from starting."""
    if not is_configured():
        logger.warning("Airtable is not configured yet, skipping the schema check.")
        return
    try:
        for problem in find_schema_problems():
            logger.warning("Airtable schema check: %s", problem)
    except Exception as error:
        logger.warning("Airtable schema check failed: %s", type(error).__name__)
