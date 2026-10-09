"""Add explicit teacher-to-student authorization links."""

from alembic import op


revision = "fc3d4e5f6a7b"
down_revision = "fb2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE teacher_student_assignments(
          id uuid PRIMARY KEY,
          teacher_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          student_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_teacher_student_assignment UNIQUE (teacher_id, student_id),
          CONSTRAINT ck_teacher_student_distinct CHECK (teacher_id <> student_id)
        )"""
    )
    op.execute("CREATE INDEX ix_teacher_student_assignments_teacher_id ON teacher_student_assignments(teacher_id)")
    op.execute("CREATE INDEX ix_teacher_student_assignments_student_id ON teacher_student_assignments(student_id)")


def downgrade():
    op.execute("DROP TABLE teacher_student_assignments")
