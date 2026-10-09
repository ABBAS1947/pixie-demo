"""Runtime invariants that keep a deployed API honest about its code/schema."""

import os
import uuid

from sqlalchemy import text

from app.core.db import engine

# Keep this in one place and update it whenever a migration becomes the app's
# minimum supported schema. A process with older code must not serve traffic.
EXPECTED_DB_REVISION = "ff7d8e9f0011"
# The dashboard sticky note requires the user-scoped quick_notes table.
COMPATIBLE_DB_REVISIONS = frozenset({EXPECTED_DB_REVISION})
BUILD_REVISION = os.getenv("PIXIE_BUILD_REVISION", "workspace")
# One API process per Pixie deployment in the current supervisor setup. A new
# value on every boot lets signed-in clients detect restarts and deployments.
API_INSTANCE_ID = os.getenv("PIXIE_API_INSTANCE_ID") or uuid.uuid4().hex


async def verify_database_revision() -> str:
    """Fail fast when the process is pointed at an incompatible database."""
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        revision = result.scalar_one_or_none()
    if revision not in COMPATIBLE_DB_REVISIONS:
        raise RuntimeError(
            f"Database schema mismatch: running {revision!r}, expected one of "
            f"{sorted(COMPATIBLE_DB_REVISIONS)!r}. "
            "Run migrations before starting this API."
        )
    return revision
