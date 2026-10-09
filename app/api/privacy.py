"""Explicit reauthentication, irreversible account deletion and private receipts."""
import asyncio
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from app.api.deps import bearer, get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import decode_token
from app.models.lifecycle import DeletionRequest, ReauthenticationGrant
from app.models.lifecycle import ExportJob, SecurityEvent
from app.models.models import User
from app.services.account_lifecycle import receipt_hash, request_deletion
from app.core.rate_limit import RateLimiter, note_search_limiter

router = APIRouter(prefix="/privacy", tags=["privacy"])
deletion_status_limiter = RateLimiter(max_requests=180, window_seconds=60)


class Reauthentication(BaseModel):
    password: SecretStr | None = Field(default=None)


class DeletionConfirmation(BaseModel):
    request_id: uuid.UUID
    receipt: SecretStr = Field(min_length=43, max_length=100)
    confirmation: str = Field(pattern="^DELETE MY ACCOUNT$")
    reauthentication: str = Field(min_length=32, max_length=200)


@router.post("/reauthenticate")
async def reauthenticate(body: Reauthentication, user: User = Depends(get_current_user),
                         credentials=Depends(bearer), db=Depends(get_db)):
    note_search_limiter.check(f"reauthentication:{user.id}")
    claims = decode_token(credentials.credentials)
    if settings.deployment_mode != "development" and user.is_teacher and claims.get("aal") != "aal2":
        raise HTTPException(403, "Multi-factor authentication is required")
    now = datetime.now(timezone.utc)
    if body.password is not None:
        # Supabase validates the password; Pixie never stores it or provider tokens.
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            try:
                identity = await client.get(f"{settings.supabase_url}/auth/v1/user", headers={
                    "Authorization": f"Bearer {credentials.credentials}", "apikey": settings.supabase_public_key})
                identity.raise_for_status()
                email = identity.json()["email"]
                result = await client.post(f"{settings.supabase_url}/auth/v1/token?grant_type=password",
                    headers={"apikey": settings.supabase_public_key},
                    json={"email": email, "password": body.password.get_secret_value()})
                if result.status_code in {400, 401, 403}:
                    raise HTTPException(403, "Reauthentication failed")
                result.raise_for_status()
                if result.json()["user"]["id"] != user.auth_id:
                    raise HTTPException(403, "Reauthentication failed")
            except HTTPException:
                raise
            except (httpx.HTTPError, KeyError, ValueError):
                raise HTTPException(503, "Reauthentication is temporarily unavailable")
    else:
        # iat changes on refresh. Only a signed recent authentication-method
        # timestamp proves a new sign-in, including OAuth users.
        recent = any(isinstance(item, dict) and item.get("method") in {"password", "oauth", "totp", "webauthn"}
                     and isinstance(item.get("timestamp"), (int, float))
                     and 0 <= now.timestamp() - item["timestamp"] <= 300 for item in claims.get("amr", []))
        if not recent:
            raise HTTPException(403, "Sign in again to confirm this action")
    secret = secrets.token_urlsafe(32)
    grant = ReauthenticationGrant(id=uuid.uuid4(), user_id=user.id, secret_hash=receipt_hash(secret),
                                  action="delete_account", expires_at=now + timedelta(minutes=5))
    db.add(grant)
    await db.commit()
    return {"reauthentication": f"{grant.id}.{secret}", "expires_in": 300}


@router.post("/deletions", status_code=202)
async def delete_account(body: DeletionConfirmation, credentials=Depends(bearer), db=Depends(get_db)):
    if not settings.privacy_workers_enabled:
        raise HTTPException(503, "Account deletion is not enabled until cleanup verification is complete")
    deletion_status_limiter.check("privacy-public-deletion-starts")
    secret = body.receipt.get_secret_value()
    existing = await db.get(DeletionRequest, body.request_id)
    if existing is not None:
        # Receipt capability permits only an idempotent acknowledgment, never
        # private reads, reprovisioning or access restoration after logout.
        if not secrets.compare_digest(existing.receipt_hash, receipt_hash(secret)):
            raise HTTPException(404, "Receipt not found")
        return {"request_id": str(existing.id), "receipt": secret, "state": existing.state, "access_revoked": True}
    user = await get_current_user(credentials=credentials, db=db)
    try:
        grant_id, secret = body.reauthentication.split(".", 1)
        grant_id = uuid.UUID(grant_id)
    except ValueError:
        raise HTTPException(403, "Reauthentication is required")
    grant = (await db.execute(select(ReauthenticationGrant).where(
        ReauthenticationGrant.id == grant_id, ReauthenticationGrant.user_id == user.id,
        ReauthenticationGrant.action == "delete_account").with_for_update())).scalar_one_or_none()
    if not grant or grant.used or grant.expires_at <= datetime.now(timezone.utc) or not secrets.compare_digest(grant.secret_hash, receipt_hash(secret)):
        raise HTTPException(403, "Reauthentication is required")
    grant.used = True
    return await request_deletion(db, user, request_id=body.request_id, secret=secret)


@router.get("/deletions/{request_id}")
async def deletion_status(request_id: uuid.UUID, x_deletion_receipt: str = Header(default="", max_length=100), db=Depends(get_db)):
    # Receipt stays in a header, never an access-log URL or bearer token.
    deletion_status_limiter.check("privacy-public-receipts")
    note_search_limiter.check(f"deletion-status:{request_id}")
    request = await db.get(DeletionRequest, request_id)
    if not request or not secrets.compare_digest(request.receipt_hash, receipt_hash(x_deletion_receipt)):
        raise HTTPException(404, "Receipt not found")
    return {"state": request.state, "access_revoked": True,
            "complete": request.state == "complete"}


@router.post("/exports", status_code=202)
async def start_export(user=Depends(get_current_user), db=Depends(get_db)):
    if not settings.privacy_workers_enabled:
        raise HTTPException(503, "Private exports are not enabled until storage verification is complete")
    note_search_limiter.check(f"export:{user.id}")
    from app.services.account_lifecycle import assert_user_active
    await assert_user_active(db, user.id, lock=True)
    pending = (await db.execute(select(ExportJob.id).where(ExportJob.user_id == user.id,
        ExportJob.expires_at > datetime.now(timezone.utc), ExportJob.state.in_(["pending", "ready"])).limit(1))).first()
    if pending:
        raise HTTPException(409, "An unexpired export already exists")
    job = ExportJob(id=uuid.uuid4(), user_id=user.id, state="pending", expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.add(job)
    db.add(SecurityEvent(actor_id=user.id, resource_id=job.id, action="private_export_requested", outcome="accepted"))
    await db.commit()
    return {"job_id": str(job.id), "state": job.state}


@router.get("/exports/{job_id}")
async def export_status(job_id: uuid.UUID, user=Depends(get_current_user), db=Depends(get_db)):
    job = (await db.execute(select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id,
        ExportJob.expires_at > datetime.now(timezone.utc)))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Export not found")
    return {"state": job.state}


@router.post("/exports/{job_id}/download-ticket")
async def export_ticket(job_id: uuid.UUID, user=Depends(get_current_user), db=Depends(get_db)):
    job = (await db.execute(select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id,
        ExportJob.state == "ready", ExportJob.expires_at > datetime.now(timezone.utc)).with_for_update())).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Export not found")
    secret = secrets.token_urlsafe(32)
    job.download_hash = receipt_hash(secret)
    # A ticket narrows artifact lifetime to five minutes and is single use.
    job.expires_at = min(job.expires_at, datetime.now(timezone.utc) + timedelta(minutes=5))
    await db.commit()
    return {"ticket": secret, "expires_in": 300}


@router.get("/exports/{job_id}/download")
async def export_download(job_id: uuid.UUID, x_export_ticket: str = Header(default="", max_length=100), user=Depends(get_current_user), db=Depends(get_db)):
    from fastapi.responses import Response
    from app.services.privacy_export import download
    job = (await db.execute(select(ExportJob).where(ExportJob.id == job_id, ExportJob.user_id == user.id,
        ExportJob.state == "ready", ExportJob.expires_at > datetime.now(timezone.utc)).with_for_update())).scalar_one_or_none()
    if not job or not job.download_hash or not secrets.compare_digest(job.download_hash, receipt_hash(x_export_ticket)):
        raise HTTPException(404, "Export not found")
    data = await download(job)
    from app.services.account_lifecycle import assert_user_active
    await assert_user_active(db, user.id, lock=True)
    job.download_hash = None
    db.add(SecurityEvent(actor_id=user.id, resource_id=job.id, action="private_export_download", outcome="allowed"))
    await db.commit()
    return Response(data, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=pixie-export.zip", "Cache-Control": "no-store"})
