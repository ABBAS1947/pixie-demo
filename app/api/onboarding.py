"""Onboarding interview commit — the 6-beat flow's single write point.

The frontend runs the wizard (6 beats: name, grade, subjects, goals,
learning style, tone). The interview itself is scripted and free (no LLM
calls). Only after the pixie recaps everything and the student confirms
("did I get you right?") does the frontend call POST /onboarding/commit once.

Discrete fields land in relational tables; soft answers (struggles, learning
style, schedule, goals) are written to the user's Honcho peer as messages so
the person-model refines from them over time.

Data rules (Meesam, Aug 13 2026):
- Fully generic — no pre-known user info, no family seed data; every user gets
  the same interview and is learned from scratch.
- Minimization — we collect exactly the 6 beats' fields and nothing else.
- Isolation — every write is scoped by user_id from the validated token.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.models.models import Course, User, UserPersona
from app.services.honcho_client import HonchoClient

from app.api.users import _auth_id_from_token
router = APIRouter(tags=["onboarding"])
bearer = HTTPBearer(auto_error=False)

# Same grade rule as users.py (v2 §4 age-appropriateness): must look like a
# real school grade, not arbitrary text. Covers grouped values like
# 'Middle School (6th-8th)', 'High School (9th-12th)', 'College / University',
# plus legacy '11', 'Grade 9', '8th', '12th grade', 'College'.
_GRADE_RE = re.compile(
    r"^\s*(grade\s*)?(\d{1,2}(st|nd|rd|th)?(\s*(year|grade))?"
    r"(\s+(of\s+)?(college|university))?|college|university|"
    r"middle\s*school\s*\(.*?\)|high\s*school\s*\(.*?\)|college\s*/\s*university)\s*$",
    re.IGNORECASE,
)

_TONES = {"playful_sarcastic", "calm_steady", "blunt"}

class SubjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    hardest: bool = False


class OnboardingCommit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    grade_level: str | None = Field(default=None, max_length=50)
    tone: str | None = Field(default=None, max_length=50)
    resource_constraints: str | None = None
    subjects: list[SubjectInput] = Field(default_factory=list)
    # Soft answers — stored in Honcho, not the relational DB.
    struggles: str | None = None
    learning_style: str | None = None
    schedule: str | None = None
    goals: str | None = None

    @field_validator("grade_level")
    @classmethod
    def _validate_grade(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        if not _GRADE_RE.match(v):
            raise ValueError(
                "grade_level must look like a school grade, e.g. '11', 'Grade 9', '8th', 'High School (9th-12th)'"
            )
        return v

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        if v not in _TONES:
            raise ValueError(f"tone must be one of {sorted(_TONES)}")
        return v


@router.post("/onboarding/commit")
async def commit_onboarding(
    body: OnboardingCommit,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Commit the confirmed interview. Idempotent for re-runs: existing
    courses are skipped by (user_id, name), soft answers are re-written to
    Honcho (the person-model just gets the latest statement)."""
    auth_id = _auth_id_from_token(credentials)

    user = (
        await db.execute(
            select(User).options(selectinload(User.persona)).where(User.auth_id == auth_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Provision first via GET /users/me"
        )

    # --- discrete fields -------------------------------------------------
    if body.name:
        user.name = body.name
    if body.grade_level:
        user.grade_level = body.grade_level

    if not user.persona:
        user.persona = UserPersona()
    if body.tone:
        user.persona.tone = body.tone
    if body.resource_constraints:
        user.persona.resource_constraints = body.resource_constraints

    # --- courses (skip existing, so re-onboarding can't duplicate) -------
    created_courses = 0
    for subject in body.subjects:
        exists = (
            await db.execute(
                select(Course.id).where(
                    Course.user_id == user.id, Course.name == subject.name
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(Course(user_id=user.id, name=subject.name))
            created_courses += 1

    await db.commit()

    # --- soft answers -> Honcho (best-effort; DB is the source of truth) --
    soft: list[tuple[str, str]] = []
    if body.struggles:
        soft.append(("struggles", body.struggles))
    if body.learning_style:
        soft.append(("learning style", body.learning_style))
    if body.schedule:
        soft.append(("schedule", body.schedule))
    if body.goals:
        soft.append(("goals and deadlines", body.goals))

    honcho_written = 0
    if soft:
        try:
            honcho = HonchoClient()
            session = await honcho.create_session(user.honcho_peer_id)
            session_id = session.get("id") or session.get("session_id")
            for label, text in soft:
                if session_id:
                    await honcho.add_message(
                        session_id,
                        f"Onboarding — {label}: {text}",
                        peer_name=user.honcho_peer_id,
                    )
                    honcho_written += 1
        except Exception:
            # Never fail a confirmed onboarding because Honcho hiccuped.
            honcho_written = 0

    return {
        "committed": True,
        "user_id": str(user.id),
        "courses_created": created_courses,
        "honcho_answers_written": honcho_written,
    }
