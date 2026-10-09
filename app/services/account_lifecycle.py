"""Immediate access fences plus durable, externally reconciled deletion."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.lifecycle import DeletionRequest, SecurityEvent
from app.models.models import User
from app.services.content_crypto import atomic_private_write


def receipt_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def ledger_path(auth_id: str) -> Path:
    return Path(settings.deletion_ledger_root) / f"{receipt_hash(auth_id)}.json"


async def assert_auth_active(db, auth_id: str):
    # This external ledger is deliberately not rolled back with DB snapshots.
    if ledger_path(auth_id).exists():
        raise HTTPException(401, "Account access has been revoked")
    blocked = (await db.execute(select(DeletionRequest.id).where(DeletionRequest.auth_id == auth_id))).scalar_one_or_none()
    if blocked:
        raise HTTPException(401, "Account access has been revoked")


async def assert_user_active(db, user_id, *, lock=False):
    query = select(User.account_state).where(User.id == user_id)
    if lock:
        query = query.with_for_update()
    state = (await db.execute(query)).scalar_one_or_none()
    if state != "active":
        raise HTTPException(401, "Account access has been revoked")


async def request_deletion(db, user: User, *, request_id: uuid.UUID, secret: str):
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = (await db.execute(select(DeletionRequest).where(DeletionRequest.user_id == user.id))).scalar_one_or_none()
    if existing:
        if existing.id == request_id and secrets.compare_digest(existing.receipt_hash, receipt_hash(secret)):
            return {"request_id": str(existing.id), "receipt": secret, "state": existing.state, "access_revoked": True}
        raise HTTPException(409, "Deletion has already been requested")
    now = datetime.now(timezone.utc)
    request = DeletionRequest(id=request_id, user_id=user.id, auth_id=user.auth_id,
                              peer_id=user.honcho_peer_id, receipt_hash=receipt_hash(secret),
                              backup_expiry=now + timedelta(days=7), state="pending", targets={})
    user.account_state = "deleting"
    db.add(request)
    db.add(SecurityEvent(actor_id=user.id, resource_id=request.id, action="account_deletion_requested", outcome="accepted"))
    # Write fence before committing. If commit fails, fence remains fail-closed
    # and operator reconciliation reconstructs the pending request from it.
    atomic_private_write(ledger_path(user.auth_id), json.dumps({
        "id": str(request.id), "user_id": str(user.id), "auth_id": user.auth_id,
        "peer_id": user.honcho_peer_id, "receipt_hash": request.receipt_hash,
        "created_at": now.isoformat(), "backup_expiry": request.backup_expiry.isoformat(),
    }, sort_keys=True).encode())
    await db.commit()
    return {"request_id": str(request.id), "receipt": secret, "state": "pending", "access_revoked": True}
