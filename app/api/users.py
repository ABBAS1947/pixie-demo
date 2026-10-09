"""User provisioning — first-login flow.

The auth_id comes ONLY from the validated JWT (never the request body).
/users/me auto-provisions: first call creates the users row (pinned Honcho
peer + vault folder), subsequent calls return the existing row. Idempotent.
"""

import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.security import AuthVerificationUnavailable, decode_token
from app.models.models import User, UserPersona
from app.services.honcho_client import HonchoClient
from app.services.account_lifecycle import assert_auth_active, assert_user_active
from app.services.content_crypto import registry

router = APIRouter(tags=["users"])

bearer = HTTPBearer(auto_error=False)

# v2 §4 age-appropriateness: grade_level must be a plausible school grade,
# not arbitrary text ("999", "preschool-professor"). Free-form enough to
# cover "11", "Grade 11", "9th", "12th grade", "1st year university",
# "College" — strict enough to reject garbage.
_GRADE_RE = re.compile(
    r"^\s*(grade\s*)?(\d{1,2}(st|nd|rd|th)?(\s*(year|grade))?"
    r"(\s+(of\s+)?(college|university))?|college|university)\s*$",
    re.IGNORECASE,
)


class OnboardingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    grade_level: str | None = Field(default=None, max_length=20)
    tone: str | None = Field(default=None, max_length=50)
    resource_constraints: str | None = None
    birth_year: int | None = Field(default=None, description="Student birth year (age gate)")
    timezone: str | None = Field(default=None, description="IANA timezone name, e.g. Asia/Dubai")

    @field_validator("grade_level")
    @classmethod
    def _validate_grade(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        if not _GRADE_RE.match(v):
            raise ValueError("grade_level must look like a school grade, e.g. '11', 'Grade 9', '8th'")
        return v

    @field_validator("birth_year")
    @classmethod
    def _validate_birth_year(cls, v: int | None) -> int | None:
        if v is None:
            return v
        from datetime import datetime, timezone
        this_year = datetime.now(timezone.utc).year
        if not (1990 <= v <= this_year):
            raise ValueError(f"birth_year must be between 1990 and {this_year}")
        return v


def _peer_id_for(auth_id: str) -> str:
    """Stable, pinned peer identity derived once from auth_id."""
    return f"sp-{uuid.uuid5(uuid.NAMESPACE_URL, auth_id)}"


def _vault_path_for(auth_id: str) -> str:
    return os.path.join(settings.vault_root, "users", _peer_id_for(auth_id))


def _auth_id_from_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_token(credentials.credentials)
    except AuthVerificationUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication verification is temporarily unavailable")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    auth_id = claims.get("sub")
    if not auth_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")
    from app.services.account_lifecycle import ledger_path
    if ledger_path(auth_id).exists():
        raise HTTPException(401, "Account access has been revoked")
    from app.services.processing_boundary import bind_auth
    bind_auth(auth_id)
    return auth_id


async def require_teacher(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Teacher-only guard. Students get 403. Used by teacher dashboard APIs."""
    auth_id = _auth_id_from_token(credentials)
    await assert_auth_active(db, auth_id)
    user = (
        await db.execute(select(User).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not provisioned")
    if not user.is_teacher:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Teacher access only")
    await assert_user_active(db, user.id)
    from app.services.processing_boundary import bind_actor
    bind_actor(user.id)
    if settings.deployment_mode != "development" and decode_token(credentials.credentials).get("aal") != "aal2":
        raise HTTPException(403, "Multi-factor authentication is required")
    return user


@router.get("/users/me")
async def get_me(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auto-provision on first login; return the user. Idempotent."""
    auth_id = _auth_id_from_token(credentials)

    await assert_auth_active(db, auth_id)

    user = (
        await db.execute(select(User).options(selectinload(User.persona)).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is not None:
        await assert_user_active(db, user.id)
        persona = user.persona
        return {
            "created": False,
            "user_id": str(user.id),
            "name": user.name,
            "grade_level": user.grade_level,
            "birth_year": user.birth_year,
            "is_teacher": user.is_teacher,
            "honcho_peer_id": user.honcho_peer_id,
            "vault_path": user.vault_path,
            "tone": persona.tone if persona else None,
            "resource_constraints": persona.resource_constraints if persona else None,
        }

    # Never reuse an old learner's storage/memory identity after registration.
    user_id = uuid.uuid4()
    peer_id = f"sp-{uuid.uuid4()}"
    vault_path = os.path.join(settings.vault_root, "users", str(user_id))
    if settings.content_encryption_mode == "required":
        import asyncio
        await asyncio.to_thread(registry.provision, "private", str(user_id))

    user = User(
        id=user_id,
        name=auth_id.split("@")[0] if "@" in auth_id else f"Student {auth_id[:8]}",  # placeholder until onboarding fills the real name
        honcho_peer_id=peer_id,
        vault_path=vault_path,
        auth_id=auth_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {
        "created": True,
        "user_id": str(user.id),
        "name": user.name,
        "honcho_peer_id": peer_id,
        "vault_path": vault_path,
    }


@router.put("/users/me")
async def update_me(
    body: OnboardingUpdate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fill onboarding details (name, grade, persona) after provisioning."""
    auth_id = _auth_id_from_token(credentials)
    await assert_auth_active(db, auth_id)
    user = (
        await db.execute(select(User).options(selectinload(User.persona)).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provision first via GET /users/me")

    if body.name:
        user.name = body.name
    if body.grade_level:
        user.grade_level = body.grade_level
    if body.birth_year is not None:
        user.birth_year = body.birth_year
    if body.timezone:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(body.timezone)
        except Exception:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "timezone must be a valid IANA name, e.g. 'Asia/Dubai'",
            )
        user.timezone = body.timezone
    if not user.persona:
        user.persona = UserPersona()
    if body.tone:
        user.persona.tone = body.tone
    if body.resource_constraints:
        user.persona.resource_constraints = body.resource_constraints
    await db.commit()
    return {"updated": True, "user_id": str(user.id)}


@router.delete("/users/me/data")
async def erase_my_data(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    """Full self-erase (workstream F): delete every row Pixie holds for this
    identity — lessons, turns, sessions, messages, notes, deadlines, files,
    review chain, profiles, vault folder, and the user row itself. The next
    GET /users/me provisions a fresh identity. Used by the school on request
    and by tests for hygiene."""
    # Fail explicitly rather than accepting an old client and deleting without
    # recent credential verification or an irreversible-deletion confirmation.
    raise HTTPException(409, "Use the confirmed deletion flow at /privacy/deletions")


@router.get("/privacy/statement")
async def privacy_statement():
    """Public, no auth: what Pixie stores, where, who sees it, commitments.
    Schools read this before the pilot. Versioned — bump version on change."""
    return {
        "version": 2,
        "stored": [
            "account: name, grade level, birth year (self-reported age gate)",
            "lessons: topics, per-turn signals, latencies, mastery scores",
            "study data: notes, deadlines, uploaded files, quiz attempts + scores",
            "memory: conversation insights and facts used for personalization",
        ],
        "location": "Dedicated Pixie database and object vault; AI and identity providers process permitted data under their own disclosed terms",
        "viewers": [
            "the student (own record via transcript)",
            "assigned teachers (authorized school progress and results only; no private conversations, notes, uploads or calendar)",
            "model providers (prompt text transits the configured LLM API per turn)",
        ],
        "commitments": [
            "no advertising to students, no sale of student data",
            "external personal-data processing requires verified provider terms and applicable permissions",
            "deletion immediately blocks account access; private backup copies have a seven-day retention target, with provider timelines verified separately",
            "authorized school records follow the school's documented retention schedule",
            "minor access requires verified applicable guardian and school conditions; enrollment alone is not proof of consent",
        ],
    }
