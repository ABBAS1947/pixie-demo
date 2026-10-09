"""Encryption column capacity, durable lifecycle and school ownership domains.

Schema only. Content/key migration is an explicit operator operation.
"""
from alembic import op
import sqlalchemy as sa

revision = "ff7d8e9f0011"
down_revision = "fe6b7c8d9e0f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("account_state", sa.String(20), nullable=False, server_default="active"))
    op.create_check_constraint("ck_user_account_state", "users", "account_state IN ('active','deleting')")
    # Text capacity accommodates the authenticated envelope, not just plaintext.
    for table, columns in {
        "users": ["name", "grade_level"], "sessions": ["subject"],
        "notes": ["title"], "deadlines": ["title"], "quick_items": ["content"],
        "files": ["original_name", "title", "subject"], "projects": ["title"],
        "conversation_insights": ["mood"], "student_profiles": ["learning_style", "preferred_tone"],
        "lessons": ["topic", "subject"], "lesson_items": ["title"],
    }.items():
        for column in columns:
            op.alter_column(table, column, type_=sa.Text())
    ddl = """
    CREATE TABLE encryption_migration_rows (
      table_name varchar(100) NOT NULL, row_id uuid NOT NULL,
      PRIMARY KEY(table_name,row_id)
    );
    CREATE TABLE deletion_requests (
      id uuid PRIMARY KEY, user_id uuid NOT NULL UNIQUE, auth_id varchar(255) NOT NULL UNIQUE,
      peer_id varchar(120) NOT NULL, receipt_hash varchar(64) NOT NULL,
      state varchar(30) NOT NULL DEFAULT 'pending', targets jsonb NOT NULL DEFAULT '{}',
      attempts integer NOT NULL DEFAULT 0, lease_until timestamptz, lease_token uuid,
      available_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
      backup_expiry timestamptz NOT NULL, last_error varchar(80),
      CONSTRAINT ck_deletion_state CHECK(state IN ('pending','running','retry','awaiting_expiry','complete'))
    );
    CREATE INDEX ix_deletion_available ON deletion_requests(available_at);
    CREATE TABLE security_events (
      id uuid PRIMARY KEY, actor_id uuid, school_id uuid, action varchar(60) NOT NULL,
      outcome varchar(30) NOT NULL, resource_id uuid, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE privacy_export_jobs (
      id uuid PRIMARY KEY, user_id uuid NOT NULL, state varchar(30) NOT NULL DEFAULT 'pending',
      artifact text, download_hash varchar(64), expires_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_privacy_export_jobs_user_id ON privacy_export_jobs(user_id);
    CREATE TABLE reauthentication_grants (
      id uuid PRIMARY KEY, user_id uuid NOT NULL, secret_hash varchar(64) NOT NULL,
      action varchar(30) NOT NULL, expires_at timestamptz NOT NULL, used boolean NOT NULL DEFAULT false
    );
    CREATE INDEX ix_reauthentication_grants_user_id ON reauthentication_grants(user_id);
    CREATE TABLE schools (
      id uuid PRIMARY KEY, name varchar(200) NOT NULL, retention_days integer NOT NULL,
      purpose varchar(500) NOT NULL, permissions_verified boolean NOT NULL DEFAULT false,
      enabled boolean NOT NULL DEFAULT false,
      CONSTRAINT ck_school_retention CHECK(retention_days>0)
    );
    CREATE TABLE school_classes (
      id uuid PRIMARY KEY, school_id uuid NOT NULL REFERENCES schools(id), name varchar(100) NOT NULL,
      CONSTRAINT uq_school_class_scope UNIQUE(school_id,id)
    );
    CREATE INDEX ix_school_classes_school_id ON school_classes(school_id);
    CREATE TABLE school_memberships (
      id uuid PRIMARY KEY, school_id uuid NOT NULL REFERENCES schools(id),
      user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      role varchar(20) NOT NULL, active boolean NOT NULL DEFAULT true,
      CONSTRAINT ck_school_role CHECK(role IN ('student','teacher','admin')),
      CONSTRAINT uq_school_member UNIQUE(school_id,user_id),
      CONSTRAINT uq_school_member_scope UNIQUE(school_id,id)
    );
    CREATE INDEX ix_school_memberships_school_id ON school_memberships(school_id);
    CREATE INDEX ix_school_memberships_user_id ON school_memberships(user_id);
    CREATE TABLE school_enrollments (
      id uuid PRIMARY KEY, school_id uuid NOT NULL REFERENCES schools(id),
      class_id uuid NOT NULL REFERENCES school_classes(id),
      user_id uuid REFERENCES users(id) ON DELETE SET NULL, active boolean NOT NULL DEFAULT true,
      authorization_evidence_id uuid NOT NULL,
      CONSTRAINT uq_school_enrollment_scope UNIQUE(school_id,id),
      CONSTRAINT fk_enrollment_class_scope FOREIGN KEY(school_id,class_id) REFERENCES school_classes(school_id,id)
    );
    CREATE INDEX ix_school_enrollments_school_id ON school_enrollments(school_id);
    CREATE INDEX ix_school_enrollments_user_id ON school_enrollments(user_id);
    CREATE TABLE school_teacher_assignments (
      id uuid PRIMARY KEY, school_id uuid NOT NULL REFERENCES schools(id),
      teacher_membership_id uuid NOT NULL REFERENCES school_memberships(id) ON DELETE CASCADE,
      enrollment_id uuid NOT NULL REFERENCES school_enrollments(id), active boolean NOT NULL DEFAULT true,
      CONSTRAINT uq_school_teacher_assignment UNIQUE(teacher_membership_id,enrollment_id),
      CONSTRAINT fk_assignment_member_scope FOREIGN KEY(school_id,teacher_membership_id) REFERENCES school_memberships(school_id,id) ON DELETE CASCADE,
      CONSTRAINT fk_assignment_enrollment_scope FOREIGN KEY(school_id,enrollment_id) REFERENCES school_enrollments(school_id,id)
    );
    CREATE TABLE school_records (
      id uuid PRIMARY KEY, school_id uuid NOT NULL REFERENCES schools(id),
      enrollment_id uuid NOT NULL REFERENCES school_enrollments(id), ciphertext text NOT NULL,
      version integer NOT NULL DEFAULT 1, expires_at timestamptz NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_school_record_enrollment UNIQUE(enrollment_id),
      CONSTRAINT fk_record_enrollment_scope FOREIGN KEY(school_id,enrollment_id) REFERENCES school_enrollments(school_id,id)
    );
    CREATE INDEX ix_school_records_school_id ON school_records(school_id);
    CREATE INDEX ix_school_records_expires_at ON school_records(expires_at);
    """
    for statement in ddl.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Forward-only: use reviewed recovery; do not discard keys or lifecycle records")
