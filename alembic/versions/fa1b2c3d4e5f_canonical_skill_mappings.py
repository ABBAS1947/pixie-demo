"""Canonical, auditable identity shared by Learn and Review.

Revision ID: fa1b2c3d4e5f
Revises: f8b0c1d2e3f4
"""
from alembic import op

revision = "fa1b2c3d4e5f"
down_revision = "f8b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE learning_skill_mappings(
      id uuid PRIMARY KEY,
      source_type text NOT NULL CHECK(source_type IN ('review_concept','learn_chunk')),
      source_id uuid NOT NULL,
      skill_code varchar(160) NOT NULL,
      skill_version integer NOT NULL,
      status text NOT NULL CHECK(status IN ('proposed','approved','rejected')),
      rationale text NOT NULL,
      approved_by uuid REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(source_type, source_id),
      FOREIGN KEY(skill_code, skill_version) REFERENCES learning_skills(code,version)
    )
    """)
    op.execute("CREATE INDEX learning_skill_mappings_skill ON learning_skill_mappings(skill_code,skill_version)")


def downgrade():
    op.execute("DROP TABLE learning_skill_mappings")
