"""Memory Retrieval Service — orchestrates what memories to inject into each turn.

Builds a structured memory context string from:
1. Active student facts (preferences, confusions, strengths, etc.)
2. Recent session insights (last 3)
3. Relevant past conversations (semantic search)
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import ConversationInsight, StudentFact, StudentProfile
from app.services.semantic_memory import search_conversations

logger = logging.getLogger(__name__)


def _format_facts(facts: list[StudentFact]) -> str:
    """Format student facts into a readable block for the prompt."""
    lines = []
    # Group by category, then by type
    by_category: dict[str, list[StudentFact]] = {}
    for f in facts:
        by_category.setdefault(f.category, []).append(f)

    for category, cat_facts in sorted(by_category.items()):
        lines.append(f"  [{category}]")
        for f in cat_facts:
            confidence_pct = f"{f.confidence:.0%}"
            lines.append(f"    - ({f.fact_type}, {confidence_pct}) {f.content}")
        lines.append("")

    return "\n".join(lines).strip()


def _format_insights(insights: list[ConversationInsight]) -> str:
    """Format recent insights into a readable block."""
    lines = []
    for ins in insights:
        topics = ", ".join(ins.topics[:5]) if ins.topics else "N/A"
        lines.append(
            f"  - Session: {topics} | Mood: {ins.mood} | "
            f"Score: {ins.sentiment_score:+.1f}"
        )
        if ins.summary:
            lines.append(f"    Summary: {ins.summary[:150]}")
    return "\n".join(lines)


def _format_messages(messages) -> str:
    """Format relevant past messages for context."""
    lines = []
    for msg in messages:
        role = "Student" if msg.role == "user" else "Pixie"
        content = msg.content[:200].replace("\n", " ")
        lines.append(f"  {role}: {content}")
    return "\n".join(lines)


async def _get_active_facts(
    db: AsyncSession, user_id: uuid.UUID
) -> list[StudentFact]:
    """Get all active, non-expired facts for the user."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(StudentFact).where(
            StudentFact.user_id == user_id,
            StudentFact.is_active == True,  # noqa: E712
            (
                (StudentFact.expires_at.is_(None))
                | (StudentFact.expires_at > now)
            ),
        )
        .order_by(StudentFact.confidence.desc())
        .limit(30)  # Cap at 30 most confident facts
    )
    return list(result.scalars().all())


async def _get_recent_insights(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 3
) -> list[ConversationInsight]:
    """Get the most recent session insights."""
    result = await db.execute(
        select(ConversationInsight)
        .where(ConversationInsight.user_id == user_id)
        .order_by(ConversationInsight.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def build_memory_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_message: str | None = None,
) -> str:
    """Build a structured memory context string for the system prompt.

    Combines active facts, recent insights, and relevant past conversations
    into a single string that gets injected into the prompt builder.
    """
    parts = []

    # 1. Active facts
    try:
        facts = await _get_active_facts(db, user_id)
        if facts:
            parts.append(
                "What Pixie knows about this student:\n"
                + _format_facts(facts)
            )
    except Exception as e:
        logger.warning("Failed to load student facts: %s", e)

    # 2. Recent insights (last 3)
    try:
        insights = await _get_recent_insights(db, user_id, limit=3)
        if insights:
            parts.append(
                "Recent sessions:\n" + _format_insights(insights)
            )
    except Exception as e:
        logger.warning("Failed to load recent insights: %s", e)

    # 3. Relevant past conversations (semantic search)
    if current_message:
        try:
            relevant = await search_conversations(
                db, user_id, current_message, limit=3
            )
            if relevant:
                parts.append(
                    "Relevant past discussions:\n"
                    + _format_messages(relevant)
                )
        except Exception as e:
            logger.warning("Failed to search conversation memory: %s", e)

    return "\n\n".join(parts)
