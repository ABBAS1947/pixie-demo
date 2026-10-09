"""Teacher access is restricted to assigned school projections."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from app.api.users import require_teacher
from app.core.db import get_db
from app.models.lifecycle import SecurityEvent
from app.services.school_records import accessible_records, decode_record
router = APIRouter(tags=["teacher"])

@router.get("/teacher/overview")
async def teacher_overview(teacher=Depends(require_teacher), db=Depends(get_db)):
    rows = []
    for record in await accessible_records(db, teacher.id):
        projection = await decode_record(record)
        skills = projection.skills
        rows.append({"enrollment_id": str(record.enrollment_id), "school_id": str(record.school_id),
            "name": projection.display_name, "mastery": [s.model_dump() for s in skills],
            "avg_mastery": sum(s.mastery for s in skills) / len(skills) if skills else None,
            "completed_practice": projection.completed_practice,
            "independent_correct": projection.independent_correct,
            "updated_at": record.updated_at.isoformat()})
    db.add(SecurityEvent(actor_id=teacher.id, action="school_overview_read", outcome="allowed"))
    await db.commit()
    return {"teacher": teacher.name, "students": rows}

@router.get("/teacher/students/{enrollment_id}")
async def teacher_student_detail(enrollment_id: uuid.UUID, teacher=Depends(require_teacher), db=Depends(get_db)):
    records = await accessible_records(db, teacher.id, enrollment_id)
    if len(records) != 1:
        raise HTTPException(404, "Student record not found")
    record = records[0]
    projection = await decode_record(record)
    db.add(SecurityEvent(actor_id=teacher.id, school_id=record.school_id, resource_id=record.id,
        action="school_projection_read", outcome="allowed"))
    await db.commit()
    return {"enrollment_id": str(enrollment_id), "school_id": str(record.school_id),
        "projection": projection.model_dump(mode="json"), "updated_at": record.updated_at.isoformat()}
