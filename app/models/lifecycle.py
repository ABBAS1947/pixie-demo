"""Independent deletion records survive removal of private account rows."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.models import Base, uuid_pk


class DeletionRequest(Base):
    __tablename__ = "deletion_requests"
    __table_args__ = (CheckConstraint("state IN ('pending','running','retry','awaiting_expiry','complete')", name="ck_deletion_state"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID, unique=True, nullable=False)
    auth_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    peer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    receipt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    targets: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    backup_expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(80))


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    school_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExportJob(Base):
    __tablename__ = "privacy_export_jobs"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    artifact: Mapped[str | None] = mapped_column(Text)
    download_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReauthenticationGrant(Base):
    __tablename__ = "reauthentication_grants"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
