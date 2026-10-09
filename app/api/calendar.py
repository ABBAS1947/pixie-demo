"""Calendar API — deadlines CRUD + Google Calendar OAuth & sync.

Translation of MASTER-CALENDAR.md Part 4 (Next.js routes) into FastAPI.
All endpoints are JWT-scoped; the Google OAuth callback binds the user via
the `state` param (user_id), since the browser redirect carries no JWT.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.models import Course, Deadline, GoogleCalendarToken, User
from app.services import google_calendar as gcal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


class DeadlineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    due_at: datetime
    kind: Literal["assignment", "exam", "project"] = "assignment"
    course_id: uuid.UUID | None = None
    pace_plan: str | None = None
    confirmed: bool = True


class DeadlineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    due_at: datetime | None = None
    kind: Literal["assignment", "exam", "project"] | None = None
    course_id: uuid.UUID | None = None
    pace_plan: str | None = None
    confirmed: bool | None = None
    status: str | None = None


def _deadline_out(d: Deadline, course_name: str | None = None) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "title": d.title,
        "due_at": d.due_at.isoformat(),
        "kind": d.kind,
        "status": d.status,
        "source": d.source,
        "confirmed": d.confirmed,
        "pace_plan": d.pace_plan,
        "course_id": str(d.course_id) if d.course_id else None,
        "course": {"name": course_name} if course_name else None,
        "synced_to_google": d.synced_to_google,
        "google_event_id": d.google_event_id,
    }


async def _get_owned_deadline(db: AsyncSession, user: User, deadline_id: uuid.UUID) -> Deadline:
    d = (
        await db.execute(
            select(Deadline).where(Deadline.id == deadline_id, Deadline.user_id == user.id)
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deadline not found")
    return d


async def _verify_course(db: AsyncSession, user: User, course_id: uuid.UUID | None) -> None:
    if course_id is None:
        return
    course = (
        await db.execute(
            select(Course).where(Course.id == course_id, Course.user_id == user.id)
        )
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")


@router.get("/deadlines")
async def list_deadlines(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Deadline).where(Deadline.user_id == user.id)
    if start is not None:
        query = query.where(Deadline.due_at >= start)
    if end is not None:
        query = query.where(Deadline.due_at <= end)
    query = query.order_by(Deadline.due_at.asc())
    deadlines = (await db.execute(query)).scalars().all()

    course_ids = {d.course_id for d in deadlines if d.course_id}
    courses: dict[uuid.UUID, str] = {}
    if course_ids:
        rows = (
            await db.execute(select(Course).where(Course.id.in_(course_ids)))
        ).scalars().all()
        courses = {c.id: c.name for c in rows}
    return {
        "deadlines": [_deadline_out(d, courses.get(d.course_id)) for d in deadlines]
    }


@router.post("/deadlines", status_code=status.HTTP_201_CREATED)
async def create_deadline(
    body: DeadlineCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _verify_course(db, user, body.course_id)
    d = Deadline(
        user_id=user.id,
        title=body.title,
        due_at=body.due_at,
        kind=body.kind,
        course_id=body.course_id,
        pace_plan=body.pace_plan,
        confirmed=body.confirmed,
        source="manual",
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    # Best-effort push to Google when connected; never fail the create on sync.
    try:
        await gcal.push_deadline(db, user, d)
        await db.commit()
        await db.refresh(d)
    except (gcal.CalendarNotConnected, gcal.CalendarNotConfigured):
        pass
    return _deadline_out(d)


@router.put("/deadlines/{deadline_id}")
async def update_deadline(
    deadline_id: uuid.UUID,
    body: DeadlineUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    d = await _get_owned_deadline(db, user, deadline_id)
    if body.course_id is not None:
        await _verify_course(db, user, body.course_id)
    if body.title is not None:
        d.title = body.title
    if body.due_at is not None:
        d.due_at = body.due_at
    if body.kind is not None:
        d.kind = body.kind
    if body.course_id is not None:
        d.course_id = body.course_id
    if body.pace_plan is not None:
        d.pace_plan = body.pace_plan
    if body.confirmed is not None:
        d.confirmed = body.confirmed
    if body.status is not None:
        d.status = body.status
    await db.commit()
    if d.synced_to_google:
        try:
            await gcal.push_deadline(db, user, d)
            await db.commit()
        except (gcal.CalendarNotConnected, gcal.CalendarNotConfigured):
            pass
    await db.refresh(d)
    return _deadline_out(d)


@router.delete("/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deadline(
    deadline_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    d = await _get_owned_deadline(db, user, deadline_id)
    event_id = d.google_event_id
    await db.delete(d)
    await db.commit()
    if event_id:
        try:
            await gcal.delete_google_event(db, user, event_id)
            await db.commit()
        except (gcal.CalendarNotConnected, gcal.CalendarNotConfigured):
            pass
    return None


@router.get("/google/authorize")
async def google_authorize(user: User = Depends(get_current_user)) -> dict:
    from app.core.rate_limit import oauth_limiter
    from app.services.oauth_state import OAuthStateLimitExceeded

    oauth_limiter.check(f"oauth:{user.id}")
    try:
        url = gcal.build_auth_url(str(user.id))
    except gcal.CalendarNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except OAuthStateLimitExceeded as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e))
    return {"url": url}


@router.get("/google/callback")
async def google_callback(
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    if not code:
        return RedirectResponse("/app/calendar?error=no_code")

    # SECURITY (HIGH-01): Consume the one-time nonce to bind the callback
    # to the originating user. This replaces the previous raw UUID state,
    # which was vulnerable to account-linking CSRF.
    from app.services.oauth_state import consume_oauth_state
    result = consume_oauth_state(state) if state else None
    if result is None:
        logger.warning("OAuth callback with invalid/expired/already-used state")
        return RedirectResponse("/app/calendar?error=auth_failed")
    user_id_str, code_verifier = result

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return RedirectResponse("/app/calendar?error=auth_failed")

    try:
        tokens = await gcal.exchange_code(code, code_verifier=code_verifier)
    except Exception as e:  # noqa: BLE001 — Google errors are varied
        logger.warning("Google OAuth exchange failed: %s", e)
        return RedirectResponse(f"/app/calendar?error={quote(str(e)[:80])}")

    # SECURITY (HIGH-08): Encrypt tokens at rest before storing in DB.
    from app.services.token_encryption import encrypt_token
    row = GoogleCalendarToken(
        user_id=user_id,
        access_token=encrypt_token(tokens["access_token"]),
        refresh_token=encrypt_token(tokens["refresh_token"]),
        expires_at=tokens["expires_at"],
        email=tokens.get("email"),
    )
    await db.merge(row)
    await db.commit()
    return RedirectResponse("/app/calendar")


@router.get("/google/status")
async def google_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    connected = await gcal.is_connected(db, user)
    details = await gcal.connection_details(db, user) if connected else None
    return {"connected": connected, "details": details}


@router.post("/google/disconnect")
async def google_disconnect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            select(GoogleCalendarToken).where(GoogleCalendarToken.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"success": True}


@router.post("/sync")
async def trigger_sync(
    full: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        if full:
            result = await gcal.full_sync(db, user)
            return {"success": True, **result}
        pushed = await gcal.sync_to_google(db, user)
        return {"success": True, "pushed": pushed}
    except gcal.CalendarNotConnected as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except gcal.CalendarNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
