"""Leased deletion with per-target outcomes. No inferred supplier completion."""
import asyncio
import json
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy import select, update

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.lifecycle import DeletionRequest, ExportJob, ReauthenticationGrant
from app.models.models import User
from app.models.school import SchoolEnrollment
from app.services.account_lifecycle import ledger_path
from app.services.content_crypto import atomic_private_write, registry


def _remove_directory(root: str, component: str):
    base = Path(root).resolve()
    if not re.fullmatch(r"(?:sp-)?[a-fA-F0-9-]{36}", component):
        raise ValueError("invalid_storage_identity")
    target = base / "users" / component
    if target.is_symlink() or not target.resolve().is_relative_to(base / "users"):
        raise ValueError("unsafe_storage_target")
    if target.exists():
        shutil.rmtree(target)  # errors propagate; no false success


async def _auth(request):
    token = Path(settings.supabase_admin_key_file).read_text().strip()
    if not token or not settings.supabase_url.startswith("https://"):
        raise ValueError("auth_erasure_not_configured")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        result = await client.delete(f"{settings.supabase_url}/auth/v1/admin/users/{uuid.UUID(request.auth_id)}",
            headers={"apikey": token, "Authorization": f"Bearer {token}"})
        if result.status_code != 404:
            result.raise_for_status()


async def _honcho(request):
    # Do not guess that removing a peer deletes derived observations/sessions.
    if not settings.honcho_erasure_verified:
        raise ValueError("honcho_erasure_not_verified")
    from app.services.honcho_client import HonchoClient
    await HonchoClient().erase_peer(request.peer_id)


async def _database(request, factory=SessionLocal):
    from app.services.user_erase import erase_user_data
    async with factory() as db:
        db.sync_session.info["privacy_cleanup"] = True
        user_id = (await db.execute(select(User.id).where(User.id == request.user_id))).scalar_one_or_none()
        user = SimpleNamespace(id=user_id) if user_id else None
        if user:
            await db.execute(update(SchoolEnrollment).where(SchoolEnrollment.user_id == user.id).values(user_id=None, active=False))
            await db.execute(ExportJob.__table__.delete().where(ExportJob.user_id == user.id))
            await db.execute(ReauthenticationGrant.__table__.delete().where(ReauthenticationGrant.user_id == user.id))
            await erase_user_data(db, user)
            await db.commit()


async def run_one(factory=SessionLocal):
    now = datetime.now(timezone.utc)
    token = uuid.uuid4()
    async with factory() as db:
        request = (await db.execute(select(DeletionRequest).where(
            DeletionRequest.state != "complete", DeletionRequest.available_at <= now,
            (DeletionRequest.lease_until.is_(None)) | (DeletionRequest.lease_until < now)
        ).order_by(DeletionRequest.available_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if not request:
            return False
        request.lease_token = token
        request.lease_until = now + timedelta(minutes=5)
        request.state = "running"
        request.attempts += 1
        request_id = request.id
        await db.commit()

    outcomes = dict(request.targets)
    errors = []
    # Files first while private keys and database metadata still exist.
    operations = [
        ("authentication", lambda: _auth(request)),
        ("vault", lambda: asyncio.to_thread(_remove_directory, settings.vault_root, str(request.user_id))),
        ("legacy_vault", lambda: asyncio.to_thread(_remove_directory, settings.vault_root, request.peer_id)),
        ("uploads", lambda: asyncio.to_thread(_remove_directory, settings.FILE_STORAGE_ROOT, str(request.user_id))),
        ("database", lambda: _database(request, factory)),
        ("honcho", lambda: _honcho(request)),
    ]
    for name, operation in operations:
        if outcomes.get(name) == "complete":
            continue
        try:
            # Bound each target below the lease and honor fences before recording.
            await asyncio.wait_for(operation(), timeout=30)
            outcomes[name] = "complete"
        except Exception as exc:
            outcomes[name] = "retry"
            errors.append(type(exc).__name__)

    if outcomes.get("database") == "complete":
        try:
            await asyncio.to_thread(registry.retire, "private", str(request.user_id))
            await asyncio.to_thread(registry.retire, "integration", str(request.user_id))
            outcomes["live_keys"] = "complete"
        except Exception as exc:
            outcomes["live_keys"] = "retry"
            errors.append(type(exc).__name__)

    # Separate attestations are issued by verified backup/provider procedures.
    # Time elapsed alone cannot prove that all copies were actually purged.
    for target in ("backup_copies", "provider_copies"):
        if outcomes.get(target) != "complete":
            outcomes[target] = "awaiting_evidence"
    async with factory() as db:
        current = (await db.execute(select(DeletionRequest).where(
            DeletionRequest.id == request_id, DeletionRequest.lease_token == token,
            DeletionRequest.lease_until > datetime.now(timezone.utc)).with_for_update())).scalar_one_or_none()
        if not current:
            return True
        # Preserve attestations submitted while the worker was running.
        for key in ("backup_copies", "provider_copies"):
            if current.targets.get(key) == "complete":
                outcomes[key] = "complete"
        current.targets = outcomes
        current.state = "retry" if errors else ("complete" if all(v == "complete" for v in outcomes.values()) else "awaiting_expiry")
        current.last_error = errors[0] if errors else None
        current.available_at = datetime.now(timezone.utc) + timedelta(minutes=min(60, 2 ** min(current.attempts, 6)))
        current.lease_until = None
        current.lease_token = None
        # Mirror outcomes outside DB backups so restore can reapply them.
        fence = json.loads(ledger_path(current.auth_id).read_text())
        fence["targets"] = outcomes
        fence["state"] = current.state
        atomic_private_write(ledger_path(current.auth_id), json.dumps(fence, sort_keys=True).encode())
        await db.commit()
    return True
