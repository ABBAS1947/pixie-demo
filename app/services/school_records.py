"""Typed school-owned projections; private transcripts never enter this API."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.models.school import School, SchoolEnrollment, SchoolMembership, SchoolRecord, SchoolTeacherAssignment
from app.services.content_crypto import registry, seal, unseal

class SkillProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{0,99}$")
    mastery: float = Field(ge=0, le=1)
    attempts: int = Field(ge=0, le=1_000_000)

class AssessmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment_id: uuid.UUID
    score: float = Field(ge=0, le=100)
    assessed_at: datetime

class SchoolProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    skills: list[SkillProgress] = Field(default_factory=list, max_length=500)
    results: list[AssessmentResult] = Field(default_factory=list, max_length=500)
    completed_practice: int = Field(default=0, ge=0, le=1_000_000)
    independent_correct: int = Field(default=0, ge=0, le=1_000_000)
    suggested_skill_codes: list[str] = Field(default_factory=list, max_length=50)

    def validate_suggestions(self):
        if not set(self.suggested_skill_codes).issubset({s.code for s in self.skills}):
            raise HTTPException(422, "Suggestions must reference an included skill")

async def accessible_records(db, teacher_id, enrollment_id=None):
    query = (select(SchoolRecord).join(SchoolEnrollment, SchoolEnrollment.id == SchoolRecord.enrollment_id)
        .join(School, School.id == SchoolRecord.school_id)
        .join(SchoolTeacherAssignment, SchoolTeacherAssignment.enrollment_id == SchoolEnrollment.id)
        .join(SchoolMembership, SchoolMembership.id == SchoolTeacherAssignment.teacher_membership_id)
        .where(SchoolMembership.user_id == teacher_id, SchoolMembership.role == "teacher",
               SchoolMembership.school_id == SchoolRecord.school_id, SchoolMembership.active.is_(True),
               SchoolTeacherAssignment.active.is_(True), SchoolEnrollment.active.is_(True),
               SchoolTeacherAssignment.school_id == SchoolRecord.school_id,
               SchoolEnrollment.school_id == SchoolRecord.school_id,
               School.enabled.is_(True), School.permissions_verified.is_(True),
               SchoolRecord.expires_at > datetime.now(timezone.utc)))
    if enrollment_id is not None:
        query = query.where(SchoolEnrollment.id == enrollment_id)
    return list((await db.execute(query)).scalars().unique())

async def decode_record(record):
    content = await asyncio.to_thread(unseal, record.ciphertext, domain="school", owner=str(record.school_id),
                                    resource=str(record.enrollment_id), field="school_projection")
    return SchoolProjection.model_validate_json(content)

async def write_record(db, school: School, enrollment: SchoolEnrollment, projection: SchoolProjection):
    if not school.enabled or not school.permissions_verified or school.retention_days <= 0 or not school.purpose.strip():
        raise HTTPException(409, "School permissions and retention must be configured")
    if enrollment.school_id != school.id or not enrollment.active:
        raise HTTPException(404, "Enrollment not found")
    projection.validate_suggestions()
    await asyncio.to_thread(registry.provision, "school", str(school.id))
    ciphertext = await asyncio.to_thread(seal, projection.model_dump_json().encode(), domain="school", owner=str(school.id),
                                        resource=str(enrollment.id), field="school_projection")
    record = (await db.execute(select(SchoolRecord).where(SchoolRecord.enrollment_id == enrollment.id).with_for_update())).scalar_one_or_none()
    expires = datetime.now(timezone.utc) + timedelta(days=school.retention_days)
    if record is None:
        record = SchoolRecord(id=uuid.uuid4(), school_id=school.id, enrollment_id=enrollment.id,
                             ciphertext=ciphertext, expires_at=expires)
        db.add(record)
    else:
        record.ciphertext = ciphertext
        record.version += 1
        record.expires_at = expires
    return record
