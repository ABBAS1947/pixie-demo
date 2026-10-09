"""Student Profile Aggregator — updates the student profile after each insight.

Called after a ConversationInsight is stored. Recalculates:
- weak/strong topics from recent insights
- engagement metrics (total sessions, messages)
- streak calculation
- topic confidence scores
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import ConversationInsight, StudentProfile
from app.models.models import Message, Note, Session

logger = logging.getLogger(__name__)

# How many recent insights to consider for topic analysis
TOPIC_LOOKBACK = 20
# Thresholds for weak/strong classification
WEAK_THRESHOLD = 0.4
STRONG_THRESHOLD = 0.7
# Confidence decay per difficulty signal
DIFFICULTY_PENALTY = 0.15
# Confidence boost for clear understanding
CONFIDENCE_BOOST = 0.1


async def _get_or_create_profile(
    db: AsyncSession, user_id, grade_level: str = ""
) -> StudentProfile:
    """Get existing profile or create a new one."""
    result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = StudentProfile(user_id=user_id, grade_level=grade_level)
        db.add(profile)
        await db.flush()
    return profile


def _compute_topic_scores(
    insights: list[ConversationInsight],
) -> dict[str, float]:
    """Compute per-topic confidence scores from recent insights.

    Returns {topic_name: confidence} where confidence is 0.0-1.0.
    Topics with difficulty signals get penalized, topics without get boosted.
    """
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}

    for insight in insights:
        topics = insight.topics or []
        difficulty_map: dict[str, str] = {}
        for ds in (insight.difficulty_signals or []):
            if isinstance(ds, dict):
                topic = ds.get("topic", "")
                signal = ds.get("signal", "")
                if topic:
                    difficulty_map[topic.lower()] = signal

        for topic in topics:
            t = topic.lower()
            if t not in scores:
                scores[t] = 0.5  # start neutral
                counts[t] = 0

            counts[t] += 1
            signal = difficulty_map.get(t)
            if signal in ("confused", "struggled", "incorrect_answer", "asked_repetition"):
                scores[t] = max(0.0, scores[t] - DIFFICULTY_PENALTY)
            elif signal == "confident":
                scores[t] = min(1.0, scores[t] + CONFIDENCE_BOOST)
            else:
                # No difficulty signal = student handled it okay
                scores[t] = min(1.0, scores[t] + CONFIDENCE_BOOST * 0.5)

    return scores


def _compute_common_confusions(
    insights: list[ConversationInsight], max_items: int = 10
) -> list[dict]:
    """Extract recurring confusion patterns from recent insights."""
    confusion_counts: dict[str, int] = {}
    for insight in insights:
        for ds in (insight.difficulty_signals or []):
            if isinstance(ds, dict):
                signal = ds.get("signal", "")
                topic = ds.get("topic", "")
                if signal in ("confused", "struggled", "incorrect_answer") and topic:
                    key = f"{topic.lower()}:{signal}"
                    confusion_counts[key] = confusion_counts.get(key, 0) + 1

    # Sort by frequency, return top N
    sorted_confusions = sorted(confusion_counts.items(), key=lambda x: x[1], reverse=True)
    result = []
    for key, count in sorted_confusions[:max_items]:
        topic, signal = key.split(":", 1)
        result.append({"topic": topic, "signal": signal, "count": count})
    return result


async def _compute_session_metrics(db: AsyncSession, user_id) -> dict:
    """Compute session-level engagement metrics."""
    # Total sessions
    session_count = (
        await db.execute(
            select(func.count(Session.id)).where(Session.user_id == user_id)
        )
    ).scalar() or 0

    # Total messages
    message_count = (
        await db.execute(
            select(func.count(Message.id)).where(Message.user_id == user_id)
        )
    ).scalar() or 0

    # Total notes created
    note_count = (
        await db.execute(
            select(func.count(Note.id)).where(Note.user_id == user_id)
        )
    ).scalar() or 0

    # Average session length (from sessions with ended_at)
    avg_length_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Session.ended_at - Session.started_at) / 60.0
            )
        ).where(
            Session.user_id == user_id,
            Session.ended_at.isnot(None),
        )
    )
    avg_session_length = avg_length_result.scalar() or 0.0

    # Session frequency: sessions in last 30 days / 4 weeks
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_sessions = (
        await db.execute(
            select(func.count(Session.id)).where(
                Session.user_id == user_id,
                Session.started_at >= thirty_days_ago,
            )
        )
    ).scalar() or 0
    session_frequency = recent_sessions / 4.0  # per week

    # Streak calculation: consecutive days with at least one session
    streak = 0
    current_date = datetime.now(timezone.utc).date()
    for day_offset in range(365):  # max 1 year streak
        check_date = current_date - timedelta(days=day_offset)
        day_start = datetime.combine(check_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        has_session = (
            await db.execute(
                select(func.count(Session.id)).where(
                    Session.user_id == user_id,
                    Session.started_at >= day_start,
                    Session.started_at < day_end,
                )
            )
        ).scalar() or 0
        if has_session > 0:
            streak += 1
        else:
            break

    return {
        "total_sessions": session_count,
        "total_messages": message_count,
        "total_notes_created": note_count,
        "avg_session_length": float(avg_session_length),
        "session_frequency": session_frequency,
        "streak_days": streak,
    }


async def update_profile(
    db: AsyncSession,
    user_id,
    insight: ConversationInsight,
    grade_level: str = "",
) -> StudentProfile:
    """Update the student profile based on a new insight.

    This is the main entry point called by the post-turn pipeline.
    """
    profile = await _get_or_create_profile(db, user_id, grade_level)

    # Fetch recent insights for topic analysis
    result = await db.execute(
        select(ConversationInsight)
        .where(ConversationInsight.user_id == user_id)
        .order_by(ConversationInsight.created_at.desc())
        .limit(TOPIC_LOOKBACK)
    )
    recent_insights = list(result.scalars().all())

    # Compute topic scores
    topic_scores = _compute_topic_scores(recent_insights)

    # Classify into weak/strong
    weak_topics = []
    strong_topics = []
    for topic, confidence in topic_scores.items():
        entry = {
            "topic": topic,
            "confidence": round(confidence, 2),
            "last_seen": insight.created_at.isoformat() if insight.created_at else "",
        }
        if confidence < WEAK_THRESHOLD:
            weak_topics.append(entry)
        elif confidence > STRONG_THRESHOLD:
            strong_topics.append(entry)

    # Sort by confidence (weakest first, strongest first)
    weak_topics.sort(key=lambda x: x["confidence"])
    strong_topics.sort(key=lambda x: x["confidence"], reverse=True)

    # Update profile fields
    profile.subjects = list(set((profile.subjects or []) + (insight.subjects or [])))
    profile.weak_topics = weak_topics
    profile.strong_topics = strong_topics
    profile.common_confusions = _compute_common_confusions(recent_insights)

    # Update engagement metrics
    metrics = await _compute_session_metrics(db, user_id)
    profile.total_sessions = metrics["total_sessions"]
    profile.total_messages = metrics["total_messages"]
    profile.total_notes_created = metrics["total_notes_created"]
    profile.avg_session_length = metrics["avg_session_length"]
    profile.session_frequency = metrics["session_frequency"]
    profile.streak_days = metrics["streak_days"]

    # Update metadata
    profile.last_active = datetime.now(timezone.utc)
    profile.last_insight_at = datetime.now(timezone.utc)
    profile.profile_version += 1

    # Derive grade level from user if available and not yet set
    if grade_level and not profile.grade_level:
        profile.grade_level = grade_level

    await db.flush()
    logger.info(
        "Updated profile for user %s: v%d, %d weak topics, %d strong topics, streak=%d",
        user_id,
        profile.profile_version,
        len(weak_topics),
        len(strong_topics),
        profile.streak_days,
    )
    return profile
