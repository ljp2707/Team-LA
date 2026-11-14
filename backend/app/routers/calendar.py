"""Calendar sync: a private .ics feed of someone's tasks, and turning it on and off.

GET /calendar/{token}.ics is public, because Google Calendar fetches it without
signing in. The token is the only key, so an unknown, reset or turned-off token,
or one belonging to someone who is no longer Active, answers 404 and nothing else.

/api/me/calendar-feed lets the signed-in person turn their feed on (or get a new
link) and off.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app import permissions
from app.airtable import client
from app.airtable.schema import Users
from app.auth.deps import current_user, require_can_edit
from app.models.user import CurrentUser
from app.services import calendar_feed
from app.services.views import World

router = APIRouter(tags=["calendar"])


def _state(token: str | None, user: CurrentUser) -> dict:
    return {
        "enabled": bool(token),
        "can_turn_on": permissions.can_update_own_tasks(user.actor),
        "feed_url": calendar_feed.feed_url(token) if token else None,
        "google_url": calendar_feed.google_subscribe_url(token) if token else None,
    }


def _token_of(user_id: str) -> str | None:
    rec = World().users.get(user_id)
    return rec.calendar_token if rec else None


@router.get("/calendar/{token}.ics", include_in_schema=False)
def feed(token: str):
    world = World()
    owner = calendar_feed.user_for_token(world, token)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return Response(
        content=calendar_feed.build_feed(world, owner),
        media_type="text/calendar; charset=utf-8",
        headers={
            # The link is a secret: never cache it in shared caches or index it.
            "Cache-Control": "private, max-age=300",
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Disposition": 'inline; filename="nmu-launches.ics"',
        },
    )


@router.get("/api/me/calendar-feed")
def get_feed_settings(user: CurrentUser = Depends(current_user)):
    return _state(_token_of(user.id), user)


@router.post("/api/me/calendar-feed")
def turn_on_or_reset(user: CurrentUser = Depends(require_can_edit)):
    """Turn the feed on, or give it a new link. Any old link stops working at once."""
    token = calendar_feed.new_token()
    client.update_record(Users.TABLE, user.id, {Users.CALENDAR_FEED_TOKEN: token})
    return _state(token, user)


@router.delete("/api/me/calendar-feed")
def turn_off(user: CurrentUser = Depends(current_user)):
    """Turn the feed off. The link stops working; calendar apps then drop the events."""
    if _token_of(user.id):
        client.update_record(Users.TABLE, user.id, {Users.CALENDAR_FEED_TOKEN: None})
    return _state(None, user)
