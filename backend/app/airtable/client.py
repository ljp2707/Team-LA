"""The only code that talks to Airtable.

Airtable allows 5 requests per second per base, and locks a base out for 30 seconds
if that limit is passed. So every HTTP request waits its turn (4 per second), and
pyairtable retries with backoff if Airtable still answers 429.

Reads are cached so pages do not wait on Airtable:
- A copy younger than FRESH_SECONDS is used as is.
- An older copy, up to STALE_SECONDS, is used straight away while a fresh one is
  fetched in the background, so the next request sees it.
- Only one download of a table runs at a time. Anyone else waits for it.
- Every table is fetched in the background when the app starts.

Writes keep the app showing its own edits right away:
- The records Airtable sends back are put straight into that table's copy.
- Copies of tables whose fields are worked out from the written table (formulas,
  lookups, the other side of a link) are thrown away. See DEPENDS_ON_WRITES_TO.
- Downloads started before the write are not saved, and the touched tables are
  fetched again in the background once the writes stop.

The token stays here on the server. Never send it to the browser or log it.
"""

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from pyairtable import Api, retry_strategy

from app.airtable.schema import (
    ALL_TABLES,
    Instructors,
    Region,
    Roles,
    Session,
    Site,
    Users,
    Work,
    field_names,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

FRESH_SECONDS = 30
STALE_SECONDS = 5 * 60
SECONDS_BETWEEN_REQUESTS = 0.25  # 4 per second, just under Airtable's limit
REFRESH_AFTER_WRITE_SECONDS = 1.0  # Wait for a run of writes to finish first

# Writing the table on the left changes fields the app reads in the tables on the
# right. Keep this up to date when the app starts reading a formula, lookup or the
# other side of a link that comes from another table.
DEPENDS_ON_WRITES_TO: dict[str, set[str]] = {
    # Work's Due Date and Calculated Due Date follow the Session's Start Date.
    Session.TABLE: {Work.TABLE},
    # Site's Region Site and Session's Session Name include the region's name.
    Region.TABLE: {Site.TABLE, Session.TABLE},
    # Session Name includes the site. Instructors.Site is the other side of Site.Instructors.
    Site.TABLE: {Session.TABLE, Instructors.TABLE},
    Instructors.TABLE: {Site.TABLE},
    # Users.Roles is the other side of Roles.Users.
    Roles.TABLE: {Users.TABLE},
    Users.TABLE: {Roles.TABLE},
}

_CacheKey = tuple[str, tuple[str, ...]]

_lock = threading.Lock()
_cache: dict[_CacheKey, tuple[float, list[dict[str, Any]]]] = {}
_in_flight: dict[tuple[_CacheKey, int], Future] = {}
# Goes up for a table on every write to it, so downloads started earlier are dropped.
_generation: dict[str, int] = {}
_refresh_timer: threading.Timer | None = None
_tables_to_refresh: set[str] = set()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="airtable")

_rate_lock = threading.Lock()
_next_request_at = 0.0


def _wait_for_turn() -> None:
    """Sleep just long enough to keep requests under the rate limit."""
    global _next_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = _next_request_at - now
        _next_request_at = max(now, _next_request_at) + SECONDS_BETWEEN_REQUESTS
    if wait > 0:
        time.sleep(wait)


@lru_cache
def get_api() -> Api:
    api = Api(
        get_settings().AIRTABLE_TOKEN,
        retry_strategy=retry_strategy(total=5, backoff_factor=1),
    )
    # Every HTTP request (each page of a read, each write) waits its turn here.
    send = api.session.send

    def send_in_turn(request, **kwargs):
        _wait_for_turn()
        return send(request, **kwargs)

    api.session.send = send_in_turn
    return api


def get_base():
    return get_api().base(get_settings().AIRTABLE_BASE_ID)


def is_configured() -> bool:
    """False until real Airtable values have been put in the environment."""
    settings = get_settings()
    return bool(settings.AIRTABLE_BASE_ID) and settings.AIRTABLE_TOKEN not in (
        "",
        "pat_replace_me",
    )


# --- Reads ------------------------------------------------------------------


def _download(key: _CacheKey, generation: int, future: Future) -> None:
    table_name, fields = key
    try:
        records: list[dict[str, Any]] = []
        for page in get_base().table(table_name).iterate(fields=list(fields)):
            records.extend(page)
    except BaseException as error:
        with _lock:
            _in_flight.pop((key, generation), None)
        future.set_exception(error)
        return
    with _lock:
        _in_flight.pop((key, generation), None)
        if generation == _generation.get(table_name, 0):  # No write since it started
            _cache[key] = (time.monotonic(), records)
    future.set_result(records)


def _log_failure(table_name: str):
    def log(future: Future) -> None:
        error = future.exception()
        if error is not None:
            logger.warning("Could not refresh %s: %s", table_name, type(error).__name__)

    return log


def _fetch(key: _CacheKey, background: bool) -> Future:
    """Download a table, or join the download of it already running.

    In the background it runs on the pool. Otherwise it runs in the caller's own
    thread, so a page never queues behind background refreshes.
    """
    with _lock:
        generation = _generation.get(key[0], 0)
        future = _in_flight.get((key, generation))
        if future is not None:
            return future
        future = Future()
        _in_flight[(key, generation)] = future
    if background:
        future.add_done_callback(_log_failure(key[0]))
        _pool.submit(_download, key, generation, future)
    else:
        _download(key, generation, future)
    return future


def all_records(table_name: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
    """Return every record in a table, from the cache when it can."""
    key: _CacheKey = (table_name, tuple(fields or ()))
    with _lock:
        cached = _cache.get(key)
    if cached:
        age = time.monotonic() - cached[0]
        if age < FRESH_SECONDS:
            return cached[1]
        if age < STALE_SECONDS:
            _fetch(key, background=True)  # Ready for the next request
            return cached[1]
    return _fetch(key, background=False).result()


def warm_cache() -> None:
    """Fetch every table in the background, so the first sign in is quick."""
    if not is_configured():
        return
    for table in ALL_TABLES:
        _fetch((table.TABLE, ()), background=True)


def clear_cache() -> None:
    """Forget every cached read."""
    with _lock:
        for name in {key[0] for key in _cache} | {t.TABLE for t in ALL_TABLES}:
            _generation[name] = _generation.get(name, 0) + 1
        _cache.clear()


def _refresh_written_tables() -> None:
    with _lock:
        names = set(_tables_to_refresh)
        _tables_to_refresh.clear()
    for name in names:
        _fetch((name, ()), background=True)


def _patched(
    records: list[dict[str, Any]], changed: list[dict[str, Any]], deleted_ids: list[str]
) -> list[dict[str, Any]]:
    """The cached records with a write applied, in the same order."""
    gone = set(deleted_ids)
    replacements = {r["id"]: r for r in changed}
    out = [replacements.pop(r["id"], r) for r in records if r["id"] not in gone]
    return out + [r for r in changed if r["id"] in replacements]  # Newly created


def _after_write(
    table_name: str,
    changed: list[dict[str, Any]] | None = None,
    deleted_ids: list[str] | None = None,
) -> None:
    """Bring the cache up to date after a write to one table.

    `changed` holds the created or updated records Airtable sent back (with every
    field, formulas included). If the write failed part way, neither is given and
    that table's copy is thrown away instead.
    """
    global _refresh_timer
    affected = {table_name} | DEPENDS_ON_WRITES_TO.get(table_name, set())
    succeeded = changed is not None or deleted_ids is not None
    with _lock:
        for name in affected:
            _generation[name] = _generation.get(name, 0) + 1
        for key in list(_cache):
            name, fields = key
            if name not in affected:
                continue
            if succeeded and name == table_name and not fields:
                at, records = _cache[key]
                _cache[key] = (at, _patched(records, changed or [], deleted_ids or []))
            else:
                del _cache[key]
        if not is_configured():
            return
        # Fetch the touched tables again once the writes stop, to be sure.
        _tables_to_refresh.update(affected)
        if _refresh_timer is not None:
            _refresh_timer.cancel()
        _refresh_timer = threading.Timer(REFRESH_AFTER_WRITE_SECONDS, _refresh_written_tables)
        _refresh_timer.daemon = True
        _refresh_timer.start()


# --- Writes -----------------------------------------------------------------


BATCH_SIZE = 10  # Airtable accepts at most 10 records per write request


def _chunks(items: list, size: int = BATCH_SIZE):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def create_records(
    table_name: str, rows: list[dict[str, Any]], typecast: bool = False
) -> list[dict[str, Any]]:
    """Create rows (field dicts) in batches of 10. Returns the created records."""
    created: list[dict[str, Any]] = []
    if not rows:
        return created
    table = get_base().table(table_name)
    try:
        for chunk in _chunks(rows):
            created.extend(table.batch_create(chunk, typecast=typecast))
    except BaseException:
        _after_write(table_name)
        raise
    _after_write(table_name, changed=created)
    return created


def create_record(
    table_name: str, fields: dict[str, Any], typecast: bool = False
) -> dict[str, Any]:
    return create_records(table_name, [fields], typecast=typecast)[0]


def update_records(
    table_name: str, updates: list[dict[str, Any]], typecast: bool = False
) -> list[dict[str, Any]]:
    """Update records given as {"id": ..., "fields": {...}}, in batches of 10."""
    updated: list[dict[str, Any]] = []
    if not updates:
        return updated
    table = get_base().table(table_name)
    try:
        for chunk in _chunks(updates):
            updated.extend(table.batch_update(chunk, typecast=typecast))
    except BaseException:
        _after_write(table_name)
        raise
    _after_write(table_name, changed=updated)
    return updated


def update_record(
    table_name: str, record_id: str, fields: dict[str, Any], typecast: bool = False
) -> dict[str, Any]:
    return update_records(
        table_name, [{"id": record_id, "fields": fields}], typecast=typecast
    )[0]


def delete_records(table_name: str, record_ids: list[str]) -> None:
    """Delete rows the app owns (links, notes, drafts, unused templates).

    Projects and tasks are only deleted by projects.delete, when an admin deletes
    a whole launch. Nothing else deletes them.
    """
    if not record_ids:
        return
    table = get_base().table(table_name)
    try:
        for chunk in _chunks(record_ids):
            table.batch_delete(chunk)
    except BaseException:
        _after_write(table_name)
        raise
    _after_write(table_name, deleted_ids=record_ids)


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
