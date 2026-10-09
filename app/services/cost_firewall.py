"""Cost firewall — dual-window LLM turn budget (workstream E).

Every taught turn burns provider tokens. Two windows bound the spend:
- HOURLY_LIMIT turns in the trailing 60 minutes (absorbs bursts; a viral
  spike becomes a slope, and spacing sessions is better pedagogy anyway).
- DAILY_LIMIT turns in the trailing 24 hours (backstop on total spend).

Counts come from turn_events (one row per taught turn). Greetings and
redirects never reach the writer, so they are free by construction.
Premium users bypass both windows.

Returns "ok" | "hourly" | "daily". Callers map non-ok to a friendly
limit payload (SSE) or 429 (plain chat). Never raises on its own: a
firewall failure must fail open (log), never lock students out.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson_models import TurnEvent
from app.models.models import User
from app.models.review_models import QuizSession

logger = logging.getLogger(__name__)

HOURLY_LIMIT = 20
DAILY_LIMIT = 60

# Quiz creation burns concept/card generation calls with zero answers, so
# it gets its own tighter window: 20 built quizzes/day. Rechecks reuse
# existing cards and stay exempt.
QUIZ_CREATION_DAILY_LIMIT = 20

MESSAGES = {
    "hourly": (
        "You've used your 20 turns for this hour — Pixie needs a breather too. "
        "Your lessons are saved. Come back in a bit and we'll pick up right here."
    ),
    "daily": (
        "You've used your 60 turns for today — that's a full day of real learning. "
        "Rest, and Pixie will be ready tomorrow with your review queue."
    ),
}


async def check_turn_budget(db: AsyncSession, user: User) -> str:
    """Return 'ok', 'hourly', or 'daily'. Fails open on error."""
    try:
        if getattr(user, "is_premium", False):
            return "ok"
        now = datetime.now(timezone.utc)
        hour_n = (
            await db.execute(
                select(func.count(TurnEvent.id)).where(
                    TurnEvent.user_id == user.id,
                    TurnEvent.created_at >= now - timedelta(hours=1),
                )
            )
        ).scalar() or 0
        if hour_n >= HOURLY_LIMIT:
            return "hourly"
        day_n = (
            await db.execute(
                select(func.count(TurnEvent.id)).where(
                    TurnEvent.user_id == user.id,
                    TurnEvent.created_at >= now - timedelta(hours=24),
                )
            )
        ).scalar() or 0
        if day_n >= DAILY_LIMIT:
            return "daily"
        return "ok"
    except Exception as e:
        logger.warning("budget check failed open: %s", e)
        return "ok"


async def check_creation_budget(db: AsyncSession, user: User) -> bool:
    """True when the user may build another quiz today. Premium exempt.
    Fails open: a counting error never blocks studying."""
    try:
        if getattr(user, "is_premium", False):
            return True
        now = datetime.now(timezone.utc)
        n = (
            await db.execute(
                select(func.count(QuizSession.id)).where(
                    QuizSession.user_id == user.id,
                    QuizSession.created_at >= now - timedelta(hours=24),
                )
            )
        ).scalar() or 0
        return n < QUIZ_CREATION_DAILY_LIMIT
    except Exception as e:
        logger.warning("creation budget check failed open: %s", e)
        return True
