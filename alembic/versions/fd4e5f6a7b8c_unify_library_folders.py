"""Unify note and file folders for the Library and persist folder colors."""

from alembic import op
import sqlalchemy as sa

revision = "fd4e5f6a7b8c"
down_revision = ("fc3d4e5f6a7b", "a6b7c8d9e0f1")
branch_labels = None
depends_on = None


PALETTE = "ARRAY['#F4DFC3','#E9D5FF','#CDEFE7','#FAD2CF','#D6E6FA','#F6E6A8']::text[]"


def upgrade() -> None:
    op.add_column("folders", sa.Column("color", sa.String(7), nullable=True))
    op.execute(
        f"UPDATE folders SET color = ({PALETTE})[(1 + (abs(hashtext(id::text)::bigint) % 6))::int] WHERE color IS NULL"
    )
    op.alter_column("folders", "color", nullable=False, server_default="#F4DFC3")

    # Merge old note folders by owner and normalized name. Notes retain their
    # folder wherever a same-name shared folder already exists.
    op.execute("ALTER TABLE notes DROP CONSTRAINT fk_notes_folder_id")
    op.execute("""
        WITH duplicate_folders AS (
          SELECT id, first_value(id) OVER (
            PARTITION BY user_id, lower(trim(name)) ORDER BY created_at, id
          ) AS canonical_id
          FROM folders
        )
        UPDATE files file SET folder_id = duplicate_folders.canonical_id
        FROM duplicate_folders
        WHERE file.folder_id = duplicate_folders.id
          AND duplicate_folders.id <> duplicate_folders.canonical_id
    """)
    op.execute("""
        WITH duplicate_folders AS (
          SELECT id, first_value(id) OVER (
            PARTITION BY user_id, lower(trim(name)) ORDER BY created_at, id
          ) AS canonical_id
          FROM folders
        )
        DELETE FROM folders folder USING duplicate_folders
        WHERE folder.id = duplicate_folders.id
          AND duplicate_folders.id <> duplicate_folders.canonical_id
    """)
    op.execute("""
        INSERT INTO folders (id, user_id, name, created_at, color)
        SELECT gen_random_uuid(), nf.user_id, nf.name, nf.created_at,
               (ARRAY['#F4DFC3','#E9D5FF','#CDEFE7','#FAD2CF','#D6E6FA','#F6E6A8']::text[])
                 [(1 + (abs(hashtext(nf.id::text)::bigint) % 6))::int]
        FROM note_folders nf
        WHERE NOT EXISTS (
          SELECT 1 FROM folders f
          WHERE f.user_id = nf.user_id AND lower(trim(f.name)) = lower(trim(nf.name))
        )
    """)
    op.execute("""
        UPDATE notes n SET folder_id = f.id
        FROM note_folders nf
        JOIN folders f ON f.user_id = nf.user_id
          AND lower(trim(f.name)) = lower(trim(nf.name))
        WHERE n.folder_id = nf.id AND n.user_id = nf.user_id
    """)
    op.create_foreign_key("fk_notes_folder_id", "notes", "folders", ["folder_id"], ["id"], ondelete="SET NULL")
    op.drop_table("note_folders")

    op.add_column("files", sa.Column("note_mode", sa.String(20), nullable=False, server_default="full_text"))
    op.create_check_constraint("ck_files_note_mode", "files", "note_mode IN ('summary', 'full_text')")


def downgrade() -> None:
    # Data from merged same-name folders cannot be split back without ambiguity.
    raise RuntimeError("Library folders have been unified; restore a verified backup or roll forward.")
