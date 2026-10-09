"""Shared published tasks, authoritative evidence, idempotency and durable jobs.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from alembic import op
revision='e5f6a7b8c9d0'
down_revision='d4e5f6a7b8c9'
branch_labels=None
depends_on=None

DDL=[
"""CREATE TABLE learning_skills(code varchar(160) NOT NULL,version integer NOT NULL CHECK(version>0),
 objective text NOT NULL,published boolean NOT NULL DEFAULT false,approval text,
 PRIMARY KEY(code,version),CHECK(NOT published OR (approval IS NOT NULL AND length(btrim(approval))>0)))""",
"""CREATE TABLE learning_items(id uuid PRIMARY KEY,skill_code varchar(160) NOT NULL,skill_version integer NOT NULL,
 content jsonb NOT NULL,sequence integer NOT NULL DEFAULT 0,published boolean NOT NULL DEFAULT false,
 reserved boolean NOT NULL DEFAULT false,FOREIGN KEY(skill_code,skill_version) REFERENCES learning_skills(code,version),
 CHECK(jsonb_typeof(content)='object'),
 CHECK(NOT published OR ((content->>'approval') IS NOT NULL AND length(btrim(content->>'approval'))>0)))""",
"""CREATE TABLE learning_activities(id uuid PRIMARY KEY,user_id uuid NOT NULL REFERENCES users(id),
 skill_code varchar(160) NOT NULL,skill_version integer NOT NULL,surface text NOT NULL CHECK(surface IN ('chat_learn','review')),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','complete')),version integer NOT NULL DEFAULT 0 CHECK(version>=0),
 task_id uuid,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(id,user_id),
 FOREIGN KEY(skill_code,skill_version) REFERENCES learning_skills(code,version))""",
"""CREATE TABLE learning_tasks(id uuid PRIMARY KEY,activity_id uuid NOT NULL,user_id uuid NOT NULL,item_id uuid NOT NULL REFERENCES learning_items(id),
 content jsonb NOT NULL,supported boolean NOT NULL DEFAULT false,status text NOT NULL DEFAULT 'awaiting' CHECK(status IN ('awaiting','assessed')),
 feedback jsonb,prior_event_id uuid,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(id,activity_id),UNIQUE(id,user_id),
 FOREIGN KEY(activity_id,user_id) REFERENCES learning_activities(id,user_id))""",
"""ALTER TABLE learning_activities ADD CONSTRAINT learning_current_task_scope FOREIGN KEY(task_id,id) REFERENCES learning_tasks(id,activity_id)""",
"""CREATE TABLE learning_evidence(id uuid PRIMARY KEY,task_id uuid NOT NULL UNIQUE,user_id uuid NOT NULL,
 skill_code varchar(160) NOT NULL,skill_version integer NOT NULL,surface text NOT NULL CHECK(surface IN ('chat_learn','review')),
 purpose text NOT NULL CHECK(purpose IN ('practice','independent','delayed')),judgment text NOT NULL CHECK(judgment IN ('correct','incorrect')),
 independence text NOT NULL CHECK(independence IN ('independent','supported','unknown')),response text NOT NULL,content_hash varchar(64) NOT NULL,
 prior_event_id uuid REFERENCES learning_evidence(id),elapsed_seconds numeric,
 CHECK(purpose!='delayed' OR (prior_event_id IS NOT NULL AND elapsed_seconds>0)),
 created_at timestamptz NOT NULL DEFAULT now(),FOREIGN KEY(task_id,user_id) REFERENCES learning_tasks(id,user_id),
 FOREIGN KEY(skill_code,skill_version) REFERENCES learning_skills(code,version))""",
"""CREATE TABLE learning_starts(user_id uuid NOT NULL REFERENCES users(id),request_id uuid NOT NULL,fingerprint varchar(64) NOT NULL,
 result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(user_id,request_id))""",
"""CREATE TABLE learning_submissions(activity_id uuid NOT NULL REFERENCES learning_activities(id),request_id uuid NOT NULL,
 fingerprint varchar(64) NOT NULL,result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(activity_id,request_id))""",
"""CREATE TABLE learning_jobs(id uuid PRIMARY KEY,event_id uuid NOT NULL REFERENCES learning_evidence(id),kind text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed')),attempts integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT now(),lease_until timestamptz,lease_token uuid,last_error text,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(event_id,kind))""",
"""CREATE TABLE learning_summaries(user_id uuid NOT NULL REFERENCES users(id),skill_code varchar(160) NOT NULL,skill_version integer NOT NULL,
 counts jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(user_id,skill_code,skill_version),
 FOREIGN KEY(skill_code,skill_version) REFERENCES learning_skills(code,version))""",
"CREATE INDEX learning_items_selection ON learning_items(skill_code,skill_version,sequence) WHERE published AND NOT reserved",
"CREATE INDEX learning_tasks_owner_item ON learning_tasks(user_id,item_id)",
"CREATE INDEX learning_activities_owner ON learning_activities(user_id,created_at DESC)",
"CREATE INDEX learning_evidence_skill ON learning_evidence(user_id,skill_code,skill_version,created_at)",
"ALTER TABLE learning_tasks ADD FOREIGN KEY(prior_event_id) REFERENCES learning_evidence(id)",
"CREATE INDEX learning_jobs_ready ON learning_jobs(available_at) WHERE status IN ('pending','running')",
]

def upgrade():
    for sql in DDL: op.execute(sql)

def downgrade():
    # Evidence is learner work: a destructive downgrade requires an explicit export/restore plan.
    raise RuntimeError('Shared learning evidence cannot be discarded by downgrade. Restore a verified backup or roll forward.')
