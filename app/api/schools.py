"""School administration requires active membership in that specific school."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from app.api.users import require_teacher
from app.core.db import get_db
from app.models.lifecycle import SecurityEvent
from app.models.school import School, SchoolClass, SchoolEnrollment, SchoolMembership, SchoolRecord, SchoolTeacherAssignment
from app.models.models import User
from app.services.school_records import SchoolProjection, decode_record, write_record

router = APIRouter(prefix="/schools", tags=["schools"])

async def admin_school(db, actor, school_id):
    allowed = (await db.execute(select(SchoolMembership.id).where(
        SchoolMembership.user_id == actor.id, SchoolMembership.school_id == school_id,
        SchoolMembership.role == "admin", SchoolMembership.active.is_(True)).with_for_update())).scalar_one_or_none()
    if not allowed:
        raise HTTPException(404, "School not found")
    school = (await db.execute(select(School).where(School.id == school_id).with_for_update())).scalar_one_or_none()
    if school is None:
        raise HTTPException(404, "School not found")
    return school

class RetentionPolicy(BaseModel):
    purpose: str = Field(min_length=1, max_length=500)
    retention_days: int = Field(ge=1, le=36500)

class ClassInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class EnrollmentInput(BaseModel):
    user_id: uuid.UUID
    class_id: uuid.UUID
    authorization_evidence_id: uuid.UUID

class AssignmentInput(BaseModel):
    teacher_user_id: uuid.UUID
    enrollment_id: uuid.UUID

@router.post("/{school_id}/classes", status_code=201)
async def create_class(school_id: uuid.UUID, body: ClassInput, actor=Depends(require_teacher), db=Depends(get_db)):
    school = await admin_school(db, actor, school_id)
    if not school.enabled or not school.permissions_verified or not body.name.strip():
        raise HTTPException(409, "Verified school permissions and a class name are required")
    item = SchoolClass(id=uuid.uuid4(), school_id=school_id, name=body.name.strip())
    db.add(item)
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=item.id, action="school_class_created", outcome="allowed"))
    await db.commit()
    return {"class_id": str(item.id)}

@router.post("/{school_id}/enrollments", status_code=201)
async def enroll(school_id: uuid.UUID, body: EnrollmentInput, actor=Depends(require_teacher), db=Depends(get_db)):
    school = await admin_school(db, actor, school_id)
    if not school.enabled or not school.permissions_verified:
        raise HTTPException(409, "School enrollment is disabled")
    classroom = (await db.execute(select(SchoolClass.id).where(SchoolClass.id == body.class_id,
        SchoolClass.school_id == school_id))).scalar_one_or_none()
    target = (await db.execute(select(User.id).where(User.id == body.user_id, User.account_state == "active")
        .with_for_update())).scalar_one_or_none()
    if classroom is None or target is None:
        raise HTTPException(404, "Class or learner not found")
    member = (await db.execute(select(SchoolMembership).where(SchoolMembership.school_id == school_id,
        SchoolMembership.user_id == body.user_id).with_for_update())).scalar_one_or_none()
    if member and member.role != "student":
        raise HTTPException(409, "An institutional staff identity cannot be enrolled as a learner")
    if member is None:
        db.add(SchoolMembership(school_id=school_id, user_id=body.user_id, role="student", active=True))
    else:
        member.active = True
    # Authorization evidence is an opaque pointer to the school's independently
    # verified roster/permission record, never a transcript or uploaded ID scan.
    item = SchoolEnrollment(id=uuid.uuid4(), school_id=school_id, class_id=body.class_id, user_id=body.user_id,
        authorization_evidence_id=body.authorization_evidence_id)
    db.add(item)
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=body.authorization_evidence_id,
        action="school_enrollment_authorized", outcome="allowed"))
    await db.commit()
    return {"enrollment_id": str(item.id)}

@router.post("/{school_id}/assignments", status_code=201)
async def assign_teacher(school_id: uuid.UUID, body: AssignmentInput, actor=Depends(require_teacher), db=Depends(get_db)):
    school = await admin_school(db, actor, school_id)
    if not school.enabled or not school.permissions_verified:
        raise HTTPException(409, "School assignments are disabled")
    enrollment = (await db.execute(select(SchoolEnrollment.id).where(SchoolEnrollment.id == body.enrollment_id,
        SchoolEnrollment.school_id == school_id, SchoolEnrollment.active.is_(True)).with_for_update())).scalar_one_or_none()
    member = (await db.execute(select(SchoolMembership).where(SchoolMembership.school_id == school_id,
        SchoolMembership.user_id == body.teacher_user_id, SchoolMembership.role == "teacher",
        SchoolMembership.active.is_(True)).with_for_update())).scalar_one_or_none()
    if enrollment is None or member is None:
        raise HTTPException(404, "Enrollment or authorized teacher not found")
    assignment = (await db.execute(select(SchoolTeacherAssignment).where(
        SchoolTeacherAssignment.school_id == school_id, SchoolTeacherAssignment.teacher_membership_id == member.id,
        SchoolTeacherAssignment.enrollment_id == body.enrollment_id).with_for_update())).scalar_one_or_none()
    if assignment is None:
        assignment = SchoolTeacherAssignment(id=uuid.uuid4(), school_id=school_id,
            teacher_membership_id=member.id, enrollment_id=body.enrollment_id, active=True)
        db.add(assignment)
    else:
        assignment.active = True
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=assignment.id,
        action="school_teacher_assigned", outcome="allowed"))
    await db.commit()
    return {"assignment_id": str(assignment.id)}

@router.delete("/{school_id}/enrollments/{enrollment_id}", status_code=204)
async def end_enrollment(school_id: uuid.UUID, enrollment_id: uuid.UUID, actor=Depends(require_teacher), db=Depends(get_db)):
    await admin_school(db, actor, school_id)
    item = (await db.execute(select(SchoolEnrollment).where(SchoolEnrollment.id == enrollment_id,
        SchoolEnrollment.school_id == school_id).with_for_update())).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Enrollment not found")
    item.active = False
    await db.execute(update(SchoolTeacherAssignment).where(SchoolTeacherAssignment.school_id == school_id,
        SchoolTeacherAssignment.enrollment_id == enrollment_id).values(active=False))
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=enrollment_id,
        action="school_enrollment_ended", outcome="allowed"))
    await db.commit()

@router.put("/{school_id}/retention")
async def retention(school_id: uuid.UUID, body: RetentionPolicy, actor=Depends(require_teacher), db=Depends(get_db)):
    school = await admin_school(db, actor, school_id)
    if not body.purpose.strip():
        raise HTTPException(422, "A retention purpose is required")
    if body.retention_days < school.retention_days:
        ceiling = datetime.now(timezone.utc) + timedelta(days=body.retention_days)
        await db.execute(update(SchoolRecord).where(SchoolRecord.school_id == school_id,
                                                  SchoolRecord.expires_at > ceiling).values(expires_at=ceiling))
    school.retention_days = body.retention_days
    school.purpose = body.purpose.strip()
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, action="school_retention_changed", outcome="allowed"))
    await db.commit()
    return {"updated": True}

@router.put("/{school_id}/records/{enrollment_id}")
async def save_record(school_id: uuid.UUID, enrollment_id: uuid.UUID, body: SchoolProjection,
                      actor=Depends(require_teacher), db=Depends(get_db)):
    school = await admin_school(db, actor, school_id)
    enrollment = (await db.execute(select(SchoolEnrollment).where(SchoolEnrollment.id == enrollment_id,
        SchoolEnrollment.school_id == school_id).with_for_update())).scalar_one_or_none()
    if enrollment is None:
        raise HTTPException(404, "Enrollment not found")
    record = await write_record(db, school, enrollment, body)
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=record.id,
                         action="school_record_written", outcome="allowed"))
    await db.commit()
    return {"version": record.version}

@router.get("/{school_id}/export")
async def export_records(school_id: uuid.UUID, actor=Depends(require_teacher), db=Depends(get_db)):
    await admin_school(db, actor, school_id)
    records = list((await db.execute(select(SchoolRecord).where(SchoolRecord.school_id == school_id,
        SchoolRecord.expires_at > datetime.now(timezone.utc)).limit(1001))).scalars())
    if len(records) > 1000:
        raise HTTPException(409, "Export exceeds the bounded export limit")
    data = [{"enrollment_id": str(r.enrollment_id), "projection": (await decode_record(r)).model_dump(mode="json")} for r in records]
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, action="school_export", outcome="allowed"))
    await db.commit()
    return {"school_id": str(school_id), "records": data}

@router.delete("/{school_id}/records/{enrollment_id}", status_code=204)
async def delete_record(school_id: uuid.UUID, enrollment_id: uuid.UUID, actor=Depends(require_teacher), db=Depends(get_db)):
    await admin_school(db, actor, school_id)
    await db.execute(SchoolRecord.__table__.delete().where(SchoolRecord.school_id == school_id,
                                                         SchoolRecord.enrollment_id == enrollment_id))
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=enrollment_id,
                         action="school_record_deleted", outcome="allowed"))
    await db.commit()

@router.delete("/{school_id}/assignments/{assignment_id}", status_code=204)
async def revoke_assignment(school_id: uuid.UUID, assignment_id: uuid.UUID, actor=Depends(require_teacher), db=Depends(get_db)):
    await admin_school(db, actor, school_id)
    assignment = (await db.execute(select(SchoolTeacherAssignment).join(SchoolEnrollment,
        SchoolEnrollment.id == SchoolTeacherAssignment.enrollment_id).where(
        SchoolTeacherAssignment.id == assignment_id, SchoolEnrollment.school_id == school_id).with_for_update())).scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    assignment.active = False
    db.add(SecurityEvent(actor_id=actor.id, school_id=school_id, resource_id=assignment_id,
                         action="school_assignment_revoked", outcome="allowed"))
    await db.commit()
