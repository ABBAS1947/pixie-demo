"""Remove uploaded profile pictures and their stored files from users."""

from pathlib import Path
import re

from alembic import op
import sqlalchemy as sa


revision = "a6b7c8d9e0f1"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    # Remove only files written by the former uploader at its fixed location.
    # Unexpected paths and symlinks are left untouched rather than followed.
    from app.core.config import settings

    vault_root = Path(settings.vault_root).resolve()
    rows = op.get_bind().execute(sa.text("SELECT honcho_peer_id FROM users"))
    legacy_filenames = {"profile.jpg", "profile.jpeg", "profile.png", "profile.webp", "profile.gif"}
    for (peer_id,) in rows:
        if not re.fullmatch(r"sp-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", str(peer_id)):
            continue
        user_dir = vault_root / "users" / str(peer_id)
        profile_dir = user_dir / "profile"
        if any(path.is_symlink() for path in (vault_root / "users", user_dir, profile_dir)):
            continue
        for filename in legacy_filenames:
            target = profile_dir / filename
            if not target.is_symlink() and target.is_file():
                target.unlink()
        try:
            profile_dir.rmdir()
        except OSError:
            pass

    op.drop_column("users", "profile_picture")


def downgrade():
    # Uploaded pictures are intentionally not restored when rolling back.
    op.add_column("users", sa.Column("profile_picture", sa.String(length=500), nullable=True))
