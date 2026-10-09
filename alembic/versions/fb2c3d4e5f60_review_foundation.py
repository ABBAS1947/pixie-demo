"""Review lifecycle, immutable content, durable jobs and once-only XP receipts."""
from alembic import op

revision = 'fb2c3d4e5f60'
down_revision = 'fa1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN review_preferences jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE flashcards ADD COLUMN review_content jsonb")
    op.execute("ALTER TABLE flashcards DROP CONSTRAINT ck_flashcards_format")
    op.execute("ALTER TABLE flashcards ADD CONSTRAINT ck_flashcards_format CHECK(format IN ('mcq','short_answer','true_false','reveal_card'))")
    op.execute("ALTER TABLE quiz_items ADD COLUMN review_content jsonb, ADD COLUMN review_state jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("""ALTER TABLE quiz_sessions
      ADD COLUMN review_contract jsonb,
      ADD COLUMN request_id uuid,
      ADD COLUMN state_version integer NOT NULL DEFAULT 0 CHECK(state_version>=0),
      ADD COLUMN cursor integer NOT NULL DEFAULT 0 CHECK(cursor>=0),
      ADD COLUMN started_at timestamptz,
      ADD COLUMN last_activity_at timestamptz,
      ADD COLUMN paused_at timestamptz,
      ADD COLUMN abandoned_at timestamptz,
      ADD COLUMN abandon_reason text""")
    op.execute("ALTER TABLE quiz_sessions DROP CONSTRAINT ck_quiz_sessions_status")
    op.execute("""ALTER TABLE quiz_sessions ADD CONSTRAINT ck_quiz_sessions_status
      CHECK(status IN ('preparing','prepared','active','paused','completed','abandoned','failed'))""")
    op.execute("CREATE UNIQUE INDEX uq_review_prepare_request ON quiz_sessions(user_id,request_id) WHERE request_id IS NOT NULL")
    op.execute("CREATE INDEX review_session_history ON quiz_sessions(user_id,created_at DESC,id) WHERE review_contract IS NOT NULL")
    op.execute("""CREATE TABLE review_preparation_jobs(
      id uuid PRIMARY KEY, quiz_id uuid NOT NULL UNIQUE REFERENCES quiz_sessions(id),
      status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed','cancelled')),
      attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
      lease_token uuid, lease_until timestamptz, last_error text,
      created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX review_preparation_ready ON review_preparation_jobs(available_at,id) WHERE status IN ('pending','running')")
    op.execute("""CREATE TABLE review_request_results(
      quiz_id uuid NOT NULL REFERENCES quiz_sessions(id), request_id uuid NOT NULL,
      fingerprint varchar(64) NOT NULL, result jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(quiz_id,request_id))""")
    op.execute("""CREATE TABLE review_xp_events(
      id uuid PRIMARY KEY, quiz_id uuid NOT NULL UNIQUE REFERENCES quiz_sessions(id),
      user_id uuid NOT NULL REFERENCES users(id), policy_version text NOT NULL,
      reason text NOT NULL, requested_delta integer NOT NULL, delta integer NOT NULL,
      balance_before integer NOT NULL, balance_after integer NOT NULL CHECK(balance_after>=0),
      created_at timestamptz NOT NULL DEFAULT now(), CHECK(balance_after=balance_before+delta))""")
    op.execute("CREATE INDEX review_xp_owner ON review_xp_events(user_id,created_at DESC)")
    op.execute("""CREATE TABLE review_item_reports(
      id uuid PRIMARY KEY, quiz_id uuid NOT NULL REFERENCES quiz_sessions(id),
      item_id uuid NOT NULL REFERENCES quiz_items(id), user_id uuid NOT NULL REFERENCES users(id),
      category text NOT NULL CHECK(category IN ('incorrect_answer','ambiguous','irrelevant','accessibility','other')),
      detail text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""")


def downgrade():
    raise RuntimeError('Review answers and XP receipts are learner records; restore a verified backup or roll forward.')
