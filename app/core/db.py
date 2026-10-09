"""Async database engine + session dependency."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

# In tests (PIXIE_TESTING=1 set by tests/conftest.py) use NullPool so no
# connection is ever pooled across a TestClient's event-loop lifetime.
# Otherwise a pooled asyncpg connection stays bound to a closed loop and
# the next test crashes with "Event loop is closed". Production pools as before.
_poolclass = NullPool if os.environ.get("PIXIE_TESTING") == "1" else None
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    poolclass=_poolclass,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Alias used by the file pipeline (app/api/files.py, app/services/*).
async_session = SessionLocal

from app.services.encrypted_orm import install as _install_encryption
_install_encryption()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
