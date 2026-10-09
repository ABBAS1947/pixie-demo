"""Semantic Memory Service — embed and archive conversation messages, semantic search.

Archives messages with vector embeddings for later retrieval via cosine similarity.
Uses pgvector for native vector operations when available.
"""
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import ConversationMessage
from app.models.models import Message
from app.services.ollama_client import embed_text

logger = logging.getLogger(__name__)

# Embedding dimension (must match Vector(768) in model)
EMBEDDING_DIM = 768


async def archive_session_messages(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    """Archive all messages from a session into conversation_messages with embeddings.

    Returns the number of messages archived. Best-effort: catches errors per-message.
    """
    try:
        # Fetch messages for this session
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        messages = list(result.scalars().all())

        if not messages:
            return 0

        archived_count = 0
        for msg in messages:
            # Skip very short messages (less than 10 chars)
            if len(msg.content.strip()) < 10:
                continue

            try:
                embedding = await embed_text(msg.content[:2000])
            except Exception as e:
                logger.warning(
                    "Failed to embed message %s: %s — storing without embedding",
                    msg.id,
                    e,
                )
                embedding = None

            archived = ConversationMessage(
                session_id=session_id,
                user_id=user_id,
                role=msg.role,
                content=msg.content,
                embedding=embedding,
                created_at=msg.created_at,
            )
            db.add(archived)
            archived_count += 1

        if archived_count > 0:
            await db.flush()
            logger.info(
                "Archived %d messages for session %s",
                archived_count,
                session_id,
            )

        return archived_count

    except Exception as e:
        logger.warning(
            "Message archival failed for session %s (user %s): %s",
            session_id,
            user_id,
            e,
            exc_info=True,
        )
        return 0


async def search_conversations(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> list[ConversationMessage]:
    """Semantic search across archived conversation messages using pgvector.

    Embeds the query and finds the most similar messages using PostgreSQL
    cosine distance. Falls back to in-memory search if pgvector is unavailable.
    """
    try:
        query_embedding = await embed_text(query)
    except Exception as e:
        logger.warning("Failed to embed search query: %s", e)
        return []

    try:
        # Try pgvector cosine-distance search first
        from pgvector.sqlalchemy import Vector
        import numpy as np

        # Use pgvector's <=> operator for cosine distance
        result = await db.execute(
            select(
                ConversationMessage,
                ConversationMessage.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.embedding.isnot(None),
            )
            .order_by("distance")
            .limit(limit)
        )
        rows = result.all()
        return [row[0] for row in rows]

    except ImportError:
        logger.debug("pgvector not available, falling back to in-memory search")
    except Exception as e:
        logger.warning("pgvector search failed, falling back to in-memory: %s", e)

    # Fallback: in-memory cosine similarity
    try:
        import numpy as np

        result = await db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.embedding.isnot(None),
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(200)
        )
        messages = list(result.scalars().all())

        if not messages:
            return []

        q = np.array(query_embedding, dtype=np.float32)
        scored = []
        for msg in messages:
            if msg.embedding is None:
                continue
            try:
                m = np.array(msg.embedding, dtype=np.float32)
                sim = float(np.dot(q, m) / (np.linalg.norm(q) * np.linalg.norm(m) + 1e-10))
                scored.append((sim, msg))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [msg for _, msg in scored[:limit]]

    except Exception as e:
        logger.warning("Fallback conversation search failed: %s", e)
        return []


async def get_conversation_context(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> list[ConversationMessage]:
    """Fetch all archived messages for a specific session."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    return list(result.scalars().all())
