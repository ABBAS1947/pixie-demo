"""Provider egress fence shared by interactive and durable background work."""
from contextvars import ContextVar
from datetime import datetime, timezone
from sqlalchemy import text
from app.core.config import settings

actor_id: ContextVar[str | None] = ContextVar("pixie_processing_actor", default=None)
auth_subject: ContextVar[str | None] = ContextVar("pixie_processing_subject", default=None)

def bind_actor(user_id):
    actor_id.set(str(user_id))

def bind_auth(auth_id):
    auth_subject.set(auth_id)

def check_delivery_fence():
    from app.services.account_lifecycle import ledger_path
    subject = auth_subject.get()
    if subject and ledger_path(subject).exists():
        raise PermissionError("Account access has been revoked")

async def permit_external_processing():
    # Local development remains explicit; deployed calls require evidence plus
    # live account/consent/age authorization, never just a client checkbox.
    if settings.deployment_mode == "development":
        return
    if not settings.provider_processing_approved:
        raise PermissionError("Provider processing is not approved")
    owner = actor_id.get()
    subject = auth_subject.get()
    if owner is None and subject is None:
        raise PermissionError("Provider processing requires a learner scope")
    from app.core.db import SessionLocal
    async with SessionLocal() as db:
        predicate = "id=CAST(:id AS uuid)" if owner else "auth_id=:id"
        row = (await db.execute(text("SELECT account_state,auth_id,birth_year,review_preferences FROM users WHERE " + predicate), {"id": owner or subject})).mappings().first()
        if row is None or row["account_state"] != "active":
            raise PermissionError("Account access has been revoked")
        from app.services.account_lifecycle import assert_auth_active
        await assert_auth_active(db, row["auth_id"])
        auth_subject.set(row["auth_id"])
        if not (row["review_preferences"] or {}).get("external_processing_consent"):
            raise PermissionError("External processing consent is required")
        # Birth year alone cannot establish the exact birthday. Treat ambiguous
        # age conservatively; unknown age has the same restricted default.
        adult = row["birth_year"] is not None and datetime.now(timezone.utc).year - row["birth_year"] > 18
        if not adult:
            # Verification workflow must be implemented/approved before use.
            raise PermissionError("Minor processing authorization is not yet enabled")
