"""Google Calendar integration — OAuth2 + two-way deadline sync.

Translation of MASTER-CALENDAR.md's TypeScript CalendarService into the
FastAPI backend. Without GOOGLE_CLIENT_ID/SECRET in .env every Google call
raises CalendarNotConfigured and the calendar degrades to a plain local
deadline store (which is fully functional on its own).

All Google SDK calls are synchronous and are isolated from the async event
loop using asyncio.to_thread to prevent blocking other requests.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import CalendarSyncLog, Deadline, GoogleCalendarToken, User

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


class CalendarNotConnected(Exception):
    """User has not connected a Google account yet."""


class CalendarNotConfigured(Exception):
    """GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing from .env."""


def _check_configured() -> None:
    if not settings.google_client_id or not settings.google_client_secret:
        raise CalendarNotConfigured(
            "Google OAuth is not configured (GOOGLE_CLIENT_ID/SECRET missing from .env)."
        )


def _make_flow() -> Any:
    from google_auth_oauthlib.flow import Flow

    _check_configured()
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=GOOGLE_SCOPES,
    )


def build_auth_url(user_id: str) -> str:
    """OAuth authorize URL; uses a signed nonce as state to prevent CSRF."""
    from app.services.oauth_state import generate_oauth_state
    flow = _make_flow()
    flow.redirect_uri = settings.google_redirect_uri
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    # Store the PKCE code_verifier so the callback can exchange the code
    nonce = generate_oauth_state(user_id, code_verifier=flow.code_verifier)
    # Re-build URL with the nonce as state (the flow already set state internally,
    # but we need our custom nonce, not the flow's random state)
    from urllib.parse import urlencode, parse_qs, urlparse
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["state"] = [nonce]
    # Rebuild with our nonce
    new_query = "&".join(f"{k}={v[0]}" for k, v in params.items())
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"


def _exchange_code_sync(code: str, code_verifier: str = "") -> dict[str, Any]:
    """Synchronous token exchange — runs in a thread."""
    flow = _make_flow()
    flow.redirect_uri = settings.google_redirect_uri
    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials
    email = None
    try:
        from googleapiclient.discovery import build as gbuild
        info = gbuild("oauth2", "v2", credentials=creds).userinfo().get().execute()
        email = info.get("email")
    except Exception:
        email = None
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry,
        "email": email,
    }


async def exchange_code(code: str, code_verifier: str = "") -> dict[str, Any]:
    """Exchange the callback code for tokens (network call, offloaded to thread)."""
    return await asyncio.to_thread(_exchange_code_sync, code, code_verifier)


def _to_credentials(row: GoogleCalendarToken) -> Any:
    from google.oauth2.credentials import Credentials
    from app.services.token_encryption import decrypt_token

    return Credentials(
        token=decrypt_token(row.access_token),
        refresh_token=decrypt_token(row.refresh_token),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        expiry=row.expires_at,
    )


async def is_connected(db: AsyncSession, user: User) -> bool:
    row = (
        await db.execute(select(GoogleCalendarToken).where(GoogleCalendarToken.user_id == user.id))
    ).scalar_one_or_none()
    return row is not None


async def connection_details(db: AsyncSession, user: User) -> dict[str, Any] | None:
    row = (
        await db.execute(select(GoogleCalendarToken).where(GoogleCalendarToken.user_id == user.id))
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "email": row.email,
        "calendar_id": row.calendar_id,
        "sync_enabled": row.sync_enabled,
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
    }


def _refresh_token_sync(row: GoogleCalendarToken) -> tuple[str, datetime]:
    """Synchronous token refresh — runs in a thread."""
    creds = _to_credentials(row)
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return creds.token, creds.expiry


async def get_tokens(db: AsyncSession, user: User) -> GoogleCalendarToken:
    """Fetch tokens, refreshing the access token if expired."""
    row = (
        await db.execute(select(GoogleCalendarToken).where(GoogleCalendarToken.user_id == user.id))
    ).scalar_one_or_none()
    if row is None:
        raise CalendarNotConnected("Google Calendar is not connected.")
    if row.expires_at and row.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
        # SECURITY (HIGH-08): Encrypt refreshed token before storing.
        from app.services.token_encryption import encrypt_token
        token, expiry = await asyncio.to_thread(_refresh_token_sync, row)
        row.access_token = encrypt_token(token)
        row.expires_at = expiry
        await db.commit()
    return row


def _build_service_sync(row: GoogleCalendarToken):
    """Synchronous service build — runs in a thread."""
    from googleapiclient.discovery import build
    _check_configured()
    return build("calendar", "v3", credentials=_to_credentials(row))


async def _build_service(db: AsyncSession, user: User):
    row = await get_tokens(db, user)
    svc = await asyncio.to_thread(_build_service_sync, row)
    return svc, row


def _event_body(d: Deadline) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": d.title,
        "start": {"dateTime": d.due_at.isoformat()},
        "end": {"dateTime": (d.due_at + timedelta(minutes=30)).isoformat()},
    }
    if d.pace_plan:
        body["description"] = d.pace_plan
    return body


async def _log_sync(
    db: AsyncSession,
    user: User,
    sync_type: str,
    status: str,
    items: int = 0,
    error: str | None = None,
) -> None:
    db.add(
        CalendarSyncLog(
            user_id=user.id,
            sync_type=sync_type,
            status=status,
            items_synced=items,
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
    )


def _push_deadline_sync(svc, calendar_id: str, deadline: Deadline) -> str | None:
    """Synchronous Google API call — runs in a thread."""
    if deadline.google_event_id:
        svc.events().update(
            calendarId=calendar_id,
            eventId=deadline.google_event_id,
            body=_event_body(deadline),
        ).execute()
        return None
    else:
        created = svc.events().insert(
            calendarId=calendar_id, body=_event_body(deadline)
        ).execute()
        return created["id"]


async def push_deadline(db: AsyncSession, user: User, deadline: Deadline) -> None:
    """Create or update the mirrored Google event for one deadline."""
    svc, row = await _build_service(db, user)
    new_event_id = await asyncio.to_thread(_push_deadline_sync, svc, row.calendar_id, deadline)
    if new_event_id:
        deadline.google_event_id = new_event_id
    deadline.synced_to_google = True
    deadline.last_synced_at = datetime.now(timezone.utc)


def _delete_event_sync(svc, calendar_id: str, event_id: str) -> None:
    """Synchronous Google API call — runs in a thread."""
    try:
        svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except Exception:
        pass


async def delete_google_event(db: AsyncSession, user: User, event_id: str) -> None:
    """Remove the mirrored Google event (no-op if already gone)."""
    svc, row = await _build_service(db, user)
    await asyncio.to_thread(_delete_event_sync, svc, row.calendar_id, event_id)


def _sync_to_google_sync(svc, calendar_id: str, deadlines: list) -> tuple[int, list]:
    """Synchronous Google API calls — runs in a thread.
    Returns (count, list of (deadline_index, event_id) for new events)."""
    n = 0
    new_events = []
    for i, d in enumerate(deadlines):
        if d.source == "google_sync":
            continue
        if d.google_event_id:
            svc.events().update(
                calendarId=calendar_id,
                eventId=d.google_event_id,
                body=_event_body(d),
            ).execute()
        else:
            created = svc.events().insert(
                calendarId=calendar_id, body=_event_body(d)
            ).execute()
            new_events.append((i, created["id"]))
        n += 1
    return n, new_events


async def sync_to_google(db: AsyncSession, user: User) -> int:
    """Push local deadlines to Google (skips events imported FROM Google)."""
    svc, row = await _build_service(db, user)
    deadlines = list(
        (await db.execute(select(Deadline).where(Deadline.user_id == user.id)))
        .scalars().all()
    )
    n, new_events = await asyncio.to_thread(_sync_to_google_sync, svc, row.calendar_id, deadlines)
    # Apply new event IDs back to the objects
    for idx, event_id in new_events:
        deadlines[idx].google_event_id = event_id
    for d in deadlines:
        if d.source != "google_sync":
            d.synced_to_google = True
            d.last_synced_at = datetime.now(timezone.utc)
    row.last_sync_at = datetime.now(timezone.utc)
    await _log_sync(db, user, "pixie_to_google", "success", items=n)
    await db.commit()
    return n


def _sync_from_google_sync(svc, calendar_id: str, days: int) -> list:
    """Synchronous Google API call — runs in a thread.
    Returns list of event dicts to import."""
    now = datetime.now(timezone.utc)
    return (
        svc.events()
        .list(
            calendarId=calendar_id,
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        )
        .execute()
        .get("items", [])
    )


async def sync_from_google(db: AsyncSession, user: User, days: int = 60) -> int:
    """Import upcoming Google events as unconfirmed google_sync deadlines."""
    svc, row = await _build_service(db, user)
    events = await asyncio.to_thread(_sync_from_google_sync, svc, row.calendar_id, days)
    n = 0
    for ev in events:
        eid = ev.get("id")
        if not eid:
            continue
        existing = (
            await db.execute(
                select(Deadline).where(
                    Deadline.user_id == user.id, Deadline.google_event_id == eid
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
        if not start:
            continue
        try:
            due = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        db.add(
            Deadline(
                user_id=user.id,
                title=ev.get("summary") or "Untitled event",
                due_at=due,
                kind="assignment",
                source="google_sync",
                confirmed=True,
                google_event_id=eid,
                synced_to_google=False,
            )
        )
        n += 1
    row.last_sync_at = datetime.now(timezone.utc)
    await _log_sync(db, user, "google_to_pixie", "success", items=n)
    await db.commit()
    return n


async def full_sync(db: AsyncSession, user: User) -> dict[str, int]:
    pushed = await sync_to_google(db, user)
    imported = await sync_from_google(db, user)
    return {"pushed": pushed, "imported": imported}
