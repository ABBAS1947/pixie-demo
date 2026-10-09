"""School-owned records: no foreign key cascades from private accounts."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base, uuid_pk


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (CheckConstraint("retention_days > 0", name="ck_school_retention"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    permissions_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SchoolClass(Base):
    __tablename__ = "school_classes"
    __table_args__ = (UniqueConstraint("school_id", "id", name="uq_school_class_scope"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    school_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("schools.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class SchoolMembership(Base):
    __tablename__ = "school_memberships"
    __table_args__ = (CheckConstraint("role IN ('student','teacher','admin')", name="ck_school_role"),
                     UniqueConstraint("school_id", "user_id", name="uq_school_member"),
                     UniqueConstraint("school_id", "id", name="uq_school_member_scope"))
    id: Mapped[uuid.UUID] = uuid_pk()
    school_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("schools.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SchoolEnrollment(Base):
    __tablename__ = "school_enrollments"
    __table_args__ = (UniqueConstraint("school_id", "id", name="uq_school_enrollment_scope"),
                     ForeignKeyConstraint(["school_id", "class_id"], ["school_classes.school_id", "school_classes.id"], name="fk_enrollment_class_scope"))
    id: Mapped[uuid.UUID] = uuid_pk()
    school_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("schools.id"), nullable=False, index=True)
    class_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("school_classes.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    authorization_evidence_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)


class SchoolTeacherAssignment(Base):
    __tablename__ = "school_teacher_assignments"
    __table_args__ = (UniqueConstraint("teacher_membership_id", "enrollment_id", name="uq_school_teacher_assignment"),
                     ForeignKeyConstraint(["school_id", "teacher_membership_id"], ["school_memberships.school_id", "school_memberships.id"], ondelete="CASCADE", name="fk_assignment_member_scope"),
                     ForeignKeyConstraint(["school_id", "enrollment_id"], ["school_enrollments.school_id", "school_enrollments.id"], name="fk_assignment_enrollment_scope"))
    id: Mapped[uuid.UUID] = uuid_pk()
    school_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("schools.id"), nullable=False, index=True)
    teacher_membership_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("school_memberships.id", ondelete="CASCADE"), nullable=False)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("school_enrollments.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SchoolRecord(Base):
    __tablename__ = "school_records"
    __table_args__ = (UniqueConstraint("enrollment_id", name="uq_school_record_enrollment"),
                     ForeignKeyConstraint(["school_id", "enrollment_id"], ["school_enrollments.school_id", "school_enrollments.id"], name="fk_record_enrollment_scope"))
    id: Mapped[uuid.UUID] = uuid_pk()
    school_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("schools.id"), nullable=False, index=True)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("school_enrollments.id"), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
