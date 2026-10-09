"""Post-Turn Pipeline — orchestrates insight extraction, profile updates,
fact extraction, and message archival.

Called after a chat session ends (session idle for 5+ minutes, or manually).
Best-effort: if any step fails, logs the error and continues.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import ConversationInsight
from app.services.insight_engine import extract_insight
from app.services.profile_aggregator import update_profile

logger = logging.getLogger(__name__)


async def run_post_turn_analysis(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    grade_level: str = "",
) -> ConversationInsight | None:
    """Run the full post-turn analysis pipeline.

    1. Extract insights from the session
    2. Store the insight in conversation_insights
    3. Update the student profile
    4. Extract facts from the conversation
    5. Archive messages with embeddings

    Returns the stored ConversationInsight, or None if extraction failed
    or the session had too few messages. Errors are logged but never raised.
    """
    try:
        # Phase 1-3: Extract insights
        insight = await extract_insight(db, session_id, user_id)
        if insight is None:
            return None

        # Store the insight
        db.add(insight)
        await db.flush()
        logger.info(
            "Stored insight for session %s: topics=%s, mood=%s",
            session_id,
            insight.topics,
            insight.mood,
        )

        # Update student profile
        try:
            await update_profile(db, user_id, insight, grade_level=grade_level)
        except Exception as e:
            logger.warning(
                "Profile update failed for user %s after session %s: %s",
                user_id,
                session_id,
                e,
            )

        # Phase 4 — Extract facts
        try:
            from app.services.fact_extractor import extract_facts

            fact_count = await extract_facts(db, session_id, user_id)
            if fact_count > 0:
                logger.info(
                    "Extracted %d facts for user %s from session %s",
                    fact_count,
                    user_id,
                    session_id,
                )
        except Exception as e:
            logger.warning(
                "Fact extraction failed for session %s (user %s): %s",
                session_id,
                user_id,
                e,
            )

        # Phase 5 — Archive messages with embeddings
        try:
            from app.services.semantic_memory import archive_session_messages

            archived = await archive_session_messages(db, session_id, user_id)
            if archived > 0:
                logger.info(
                    "Archived %d messages for session %s",
                    archived,
                    session_id,
                )
        except Exception as e:
            logger.warning(
                "Message archival failed for session %s (user %s): %s",
                session_id,
                user_id,
                e,
            )

        return insight

    except Exception as e:
        logger.error(
            "Post-turn analysis failed for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        return None
