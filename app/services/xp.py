"""XP and ranks — the single source of truth for progression.

Ranks (cumulative XP, requirement doubles each step):
  Novice 0, Apprentice 40, Journeyman 120, Expert 280, Grandmaster 600.

XP sources:
  - Streak milestones: 3d=5, 7d=35, 14d=80, 20d=125, 30d=200, 60d=500, 100d=1200.
  - Learn completion: 1 XP per completed lesson, once per lesson.
  - Quiz finalize: round(avg_first_attempt_score * n_items), granted once
    per quiz (the finalize completed-transition, never replays).
"""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User

RANKS: list[tuple[int, str]] = [
    (0, "Novice"),
    (40, "Apprentice"),
    (120, "Journeyman"),
    (280, "Expert"),
    (600, "Grandmaster"),
]

STREAK_XP: dict[int, int] = {
    3: 5,
    7: 35,
    14: 80,
    20: 125,
    30: 200,
    60: 500,
    100: 1200,
}


async def lock_xp_user(session: AsyncSession, user_id: UUID) -> User:
    """Lock and refresh a learner before any XP balance mutation.

    Every writer must use this helper so concurrent quiz, Review, Learn, and
    streak awards serialize against one current balance.
    """
    return (
        await session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def award_completed_lesson_xp(
    session: AsyncSession, user_id: UUID, lesson_id: UUID
) -> bool:
    """Credit one XP once for a completed Learn lesson, atomically."""
    user = await lock_xp_user(session, user_id)
    inserted = await session.execute(
        text("""
            INSERT INTO lesson_xp_events (lesson_id, user_id, amount)
            SELECT id, user_id, 1
            FROM lessons
            WHERE id = :lesson_id AND user_id = :user_id AND phase = 'complete'
            ON CONFLICT (lesson_id) DO NOTHING
            RETURNING lesson_id
        """),
        {"lesson_id": lesson_id, "user_id": user_id},
    )
    if inserted.scalar_one_or_none() is None:
        return False
    user.xp = (user.xp or 0) + 1
    return True


def rank_for_xp(xp: int) -> str:
    """Highest rank whose threshold the XP meets."""
    name = RANKS[0][1]
    for threshold, rank_name in RANKS:
        if xp >= threshold:
            name = rank_name
    return name


def quiz_xp_for(avg_score: float, n_items: int) -> int:
    """XP for a finalized quiz: first-attempt average scaled by size."""
    if n_items <= 0 or avg_score <= 0:
        return 0
    return round(avg_score * n_items)
