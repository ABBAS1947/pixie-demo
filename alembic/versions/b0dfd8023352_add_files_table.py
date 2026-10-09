"""add_files_table

Revision ID: xxxx
Revises: b3c9d2e1a4f7
Create Date: 2026-08-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'b0dfd8023352'
down_revision = 'b3c9d2e1a4f7'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'files',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('storage_path', sa.String, nullable=False),
        sa.Column('original_name', sa.String, nullable=False),
        sa.Column('file_type', sa.String, nullable=False),
        sa.Column('file_size', sa.Integer),
        sa.Column('mime_type', sa.String),
        sa.Column('status', sa.String, server_default='pending'),
        sa.Column('needs_ocr', sa.Boolean, server_default='false'),
        sa.Column('extracted_text', sa.Text),
        sa.Column('classification', sa.String),
        sa.Column('processed_note_id', UUID(as_uuid=True), sa.ForeignKey('notes.id', ondelete='SET NULL')),
        sa.Column('uploaded_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime),
        sa.Column('error_message', sa.Text),
        sa.Column('processing_cost', sa.Integer, server_default='0'),
    )
    
    op.create_index('idx_files_user', 'files', ['user_id'])
    op.create_index('idx_files_status', 'files', ['status'])

def downgrade():
    op.drop_table('files')