"""calendar: deadlines sync columns, google_calendar_tokens, calendar_sync_logs

Revision ID: b3c9d2e1a4f7
Revises: f7a9c2e1d4b8
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c9d2e1a4f7"
down_revision = "f7a9c2e1d4b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend deadlines (MASTER-CALENDAR Part 1.2)
    op.add_column("deadlines", sa.Column("pace_plan", sa.Text(), nullable=True))
    op.add_column("deadlines", sa.Column("google_event_id", sa.String(200), nullable=True))
    op.add_column("deadlines", sa.Column("synced_to_google", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("deadlines", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deadlines", sa.Column("google_last_modified", sa.DateTime(timezone=True), nullable=True))

    # Source check now allows 'google_sync' (imported events)
    op.drop_constraint("ck_deadlines_source", "deadlines", type_="check")
    op.create_check_constraint(
        "ck_deadlines_source",
        "deadlines",
        "source IN ('manual','file_upload','conversation','google_sync')",
    )

    # 2. Google Calendar OAuth tokens (one row per user)
    op.create_table(
        "google_calendar_tokens",
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calendar_id", sa.String(100), server_default="primary", nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("sync_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. Sync logs
    op.create_table(
        "calendar_sync_logs",
        sa.Column("id", sa.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sync_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("items_synced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calendar_sync_logs_user_id", "calendar_sync_logs", ["user_id"])
    op.create_index("ix_google_calendar_tokens_user_id", "google_calendar_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("calendar_sync_logs")
    op.drop_table("google_calendar_tokens")
    op.drop_constraint("ck_deadlines_source", "deadlines", type_="check")
    op.create_check_constraint(
        "ck_deadlines_source",
        "deadlines",
        "source IN ('manual','file_upload','conversation')",
    )
    op.drop_column("deadlines", "google_last_modified")
    op.drop_column("deadlines", "last_synced_at")
    op.drop_column("deadlines", "synced_to_google")
    op.drop_column("deadlines", "google_event_id")
    op.drop_column("deadlines", "pace_plan")
