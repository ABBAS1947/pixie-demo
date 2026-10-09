"""Note retrieval — pgvector semantic search, scoped by user_id.

The vault is the source of truth for files; pgvector is the search index.
Every query filters by user_id from the token, never from the request body.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Note


async def search_notes(
    db: AsyncSession,
    user_id: uuid.UUID,
    query_embedding: list[float],
    limit: int = 5,
) -> list[Note]:
    """Return the top-N notes for this user by cosine similarity."""
    vec = Vector(query_embedding)  # type: ignore[arg-type]
    stmt = (
        select(Note)
        .where(Note.user_id == user_id)
        .order_by(Note.embedding.cosine_distance(vec))
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())
