"""Dashboard API — student home screen data.

Returns all data needed for the dashboard in one call:
- User profile (name, avatar)
- Courses (for "behind on" list)
- Concept mastery (weak topics)
- Deadlines (due tomorrow)
- Recent activity
"""

import uuid
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.models import Course, Deadline, Session, User
from app.models.lesson_models import Lesson, TurnEvent
from app.models.review_models import ConceptMastery

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class BehindTopic(BaseModel):
    name: str
    topic: str
    score: int  # confidence as percentage


class DeadlineItem(BaseModel):
    label: str
    detail: str
    id: uuid.UUID | None = None
    due_at: datetime | None = None


class RecentActivityItem(BaseModel):
    title: str
    subtitle: str


class DashboardResponse(BaseModel):
    user_id: str
    student_name: str
    day: int  # days since first lesson
    rank_name: str  # Novice | Apprentice | Journeyman | Expert | Grandmaster
    xp: int  # progression ledger total
    streak_days: int  # consecutive student-local days with a turn
    next_streak_goal: int | None  # next milestone after the current streak
    previous_streak_goal: int  # lower bound for progress within this milestone interval
    streak_earned: list[int]  # goals newly hit on this read (usually empty)
    streak_milestones: list[int]  # all persisted streak goals, for profile achievements
    behind_topics: list[BehindTopic]
    continue_topic: str | None
    continue_session_id: uuid.UUID | None = None
    timezone: str = "UTC"
    catch_up_detail: str | None
    due_label: str  # nearest deadline's student-local time range
    due_tomorrow: list[DeadlineItem]
    recent_activity: RecentActivityItem


def compute_streak(active_days: set[date], today: date) -> int:
    """Consecutive days with a turn, counting back from today.

    Today may be empty (streak stays alive through yesterday). The first
    gap ends it. Future dates never count (callers must exclude them).
    """
    day = today
    if day not in active_days:
        day -= timedelta(days=1)
        if day not in active_days:
            return 0
    streak = 0
    while day in active_days:
        streak += 1
        day -= timedelta(days=1)
    return streak


STREAK_GOALS = [3, 7, 14, 20, 30, 60, 100]


def next_streak_goal(streak: int) -> int | None:
    """First unreached goal, or None once every goal is earned."""
    for goal in STREAK_GOALS:
        if streak < goal:
            return goal
    return None


def previous_streak_goal(goal: int | None) -> int:
    """Return the milestone before goal, or zero for the first milestone."""
    if goal is None:
        return 0
    return max((candidate for candidate in STREAK_GOALS if candidate < goal), default=0)


def milestone_content(goal: int) -> str:
    return f"Streak goal reached: {goal} days"


async def award_streak_milestones(db: AsyncSession, user: User, streak: int) -> list[int]:
    """Idempotently record a milestone fact per reached goal and credit its
    XP to the user. The user-row lock serializes this check-and-award with all
    other XP writers. Returns the goals newly awarded on this call."""
    from app.models.intelligence_models import StudentFact
    from app.services.xp import STREAK_XP, lock_xp_user

    reached = [goal for goal in STREAK_GOALS if streak >= goal]
    if not reached:
        return []
    contents = [milestone_content(goal) for goal in reached]
    fact_filter = (
        StudentFact.user_id == user.id,
        StudentFact.fact_type == "milestone",
        StudentFact.content.in_(contents),
    )
    existing = set((await db.execute(select(StudentFact.content).where(*fact_filter))).scalars())
    if len(existing) == len(reached):
        return []

    # get_current_user loaded this object before the request began doing work.
    # Recheck under the lock so two dashboard reads cannot award the same goal.
    locked_user = await lock_xp_user(db, user.id)
    existing = set((await db.execute(select(StudentFact.content).where(*fact_filter))).scalars())

    awarded = []
    for goal in reached:
        content = milestone_content(goal)
        if content not in existing:
            db.add(StudentFact(
                user_id=locked_user.id,
                fact_type="milestone",
                category="behavior",
                content=content,
            ))
            locked_user.xp = (locked_user.xp or 0) + STREAK_XP.get(goal, 0)
            awarded.append(goal)
    if awarded:
        await db.commit()
        # The request's original instance is the dashboard response source.
        user.xp = locked_user.xp
    return awarded


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all dashboard data for the current user."""

    now = datetime.now(timezone.utc)
    try:
        user_tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")
    now_local = now.astimezone(user_tz)

    # ── Student name ────────────────────────────────────────────────────
    student_name = user.name or "Student"

    # ── Days since first lesson ─────────────────────────────────────────
    first_lesson = (
        await db.execute(
            select(Lesson.created_at)
            .where(Lesson.user_id == user.id)
            .order_by(Lesson.created_at)
            .limit(1)
        )
    ).scalar()
    if first_lesson:
        days_active = (now - first_lesson).days + 1
    else:
        days_active = 1

    # ── Behind topics (lowest confidence concepts) ──────────────────────
    mastery_rows = list(
        (
            await db.execute(
                select(ConceptMastery)
                .where(ConceptMastery.user_id == user.id)
                .order_by(ConceptMastery.confidence)
                .limit(3)
            )
        ).scalars().all()
    )
    behind_topics = []
    for m in mastery_rows:
        # Get concept label
        from app.models.review_models import Concept
        concept = (
            await db.execute(
                select(Concept).where(Concept.id == m.concept_id)
            )
        ).scalar_one_or_none()
        if concept:
            behind_topics.append(BehindTopic(
                name=concept.label.split("—")[0].strip() if "—" in concept.label else concept.label,
                topic=concept.label.split("—")[1].strip() if "—" in concept.label else "",
                score=int(m.confidence * 100),
            ))

    # ── Continue topic (most recently active unfinished lesson) ────────
    last_lesson = (
        await db.execute(
            select(Lesson)
            .where(Lesson.user_id == user.id, Lesson.phase != "complete")
            .order_by(Lesson.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    continue_topic = last_lesson.topic if last_lesson else None
    continue_session_id = None
    if last_lesson and last_lesson.session_id:
        continue_session_id = (
            await db.execute(
                select(Session.id).where(
                    Session.id == last_lesson.session_id,
                    Session.user_id == user.id,
                )
            )
        ).scalar_one_or_none()

    # ── Catch up detail (concepts below 50% confidence) ────────────────
    weak_count = (
        await db.execute(
            select(func.count(ConceptMastery.id)).where(
                ConceptMastery.user_id == user.id,
                ConceptMastery.confidence < 0.5,
            )
        )
    ).scalar() or 0
    catch_up_detail = f"{weak_count} concepts behind" if weak_count > 0 else None

    # ── Deadlines: nearest upcoming day, widening past tomorrow ──────────
    # Buckets use student-local dates, including today separately.
    # A fresh account with zero deadlines gets an empty label + empty list
    # and the card renders its onboarding state instead of an empty box.
    upcoming_filter = (
        Deadline.user_id == user.id,
        Deadline.due_at >= now,
        Deadline.status != "completed",
    )
    first_upcoming = (
        await db.execute(
            select(Deadline).where(*upcoming_filter).order_by(Deadline.due_at).limit(1)
        )
    ).scalar_one_or_none()
    due_label = ""
    due_tomorrow: list[DeadlineItem] = []
    if first_upcoming:
        first_day = first_upcoming.due_at.astimezone(user_tz).date()
        # A narrow UTC window covers every civil timezone, including days
        # whose midnight offset changes for daylight saving time.
        window_start = datetime.combine(first_day - timedelta(days=1), datetime.min.time(), timezone.utc)
        window_end = datetime.combine(first_day + timedelta(days=2), datetime.min.time(), timezone.utc)
        candidates = (await db.execute(
            select(Deadline).where(
                *upcoming_filter,
                Deadline.due_at >= window_start,
                Deadline.due_at < window_end,
            ).order_by(Deadline.due_at)
        )).scalars().all()
        same_day = [d for d in candidates if d.due_at.astimezone(user_tz).date() == first_day]
        delta = (first_day - now_local.date()).days
        if delta == 0:
            due_label = "Due today:"
        elif delta == 1:
            due_label = "Due tomorrow:"
        elif delta <= 7:
            due_label = "Due in the next 7 days:"
        elif delta <= 31:
            due_label = "Due in the next 31 days:"
        else:
            due_label = f"Due {first_day.strftime('%b %d')}:"
        due_tomorrow = [
            DeadlineItem(label=d.title, detail=d.kind or "", id=d.id, due_at=d.due_at)
            for d in same_day
        ]

    # ── Recent activity ────────────────────────────────────────────────
    week_ago = now - timedelta(days=7)
    week_turns = (
        await db.execute(
            select(func.count(TurnEvent.id)).where(
                TurnEvent.user_id == user.id,
                TurnEvent.created_at >= week_ago,
            )
        )
    ).scalar() or 0

    recent_activity = RecentActivityItem(
        title=f"{week_turns} study exchange{'s' if week_turns != 1 else ''}" if week_turns > 0 else "A fresh start awaits",
        subtitle="With Pixie in the last 7 days. Activity is one part of learning." if week_turns > 0 else "Your next conversation is a chance to explore something new.",
    )

    # ── Streak (consecutive student-local days with a turn) ─────────────
    # Walk newest turns first and stop at the first missing day. The indexed
    # cursor avoids transferring a student's entire history on every visit.
    turn_stream = await db.stream(
        select(TurnEvent.created_at)
        .where(TurnEvent.user_id == user.id)
        .order_by(TurnEvent.created_at.desc())
    )
    streak_days = 0
    last_day: date | None = None
    try:
        async for ts in turn_stream.scalars():
            aware = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            local_day = aware.astimezone(user_tz).date()
            if local_day > now_local.date():
                continue
            if last_day is None:
                if local_day not in (now_local.date(), now_local.date() - timedelta(days=1)):
                    break
            elif local_day == last_day:
                continue
            elif local_day != last_day - timedelta(days=1):
                break
            streak_days += 1
            last_day = local_day
    finally:
        await turn_stream.close()
    earned = await award_streak_milestones(db, user, streak_days)

    # Keep profile achievements based on the persisted milestone ledger, not
    # the current streak, which can later expire. The exact content allowlist
    # and user scope prevent unrelated student facts from entering this field.
    from app.models.intelligence_models import StudentFact

    milestone_contents = {milestone_content(goal): goal for goal in STREAK_GOALS}
    milestone_rows = await db.execute(
        select(StudentFact.content).where(
            StudentFact.user_id == user.id,
            StudentFact.fact_type == "milestone",
            StudentFact.content.in_(milestone_contents),
        )
    )
    streak_milestones = sorted({
        milestone_contents[content]
        for content in milestone_rows.scalars()
        if content in milestone_contents
    })

    from app.services.xp import rank_for_xp

    next_goal = next_streak_goal(streak_days)
    return DashboardResponse(
        user_id=str(user.id),
        student_name=student_name,
        day=days_active,
        rank_name=rank_for_xp(user.xp or 0),
        xp=user.xp or 0,
        streak_days=streak_days,
        next_streak_goal=next_goal,
        previous_streak_goal=previous_streak_goal(next_goal),
        streak_earned=earned,
        streak_milestones=streak_milestones,
        due_label=due_label,
        behind_topics=behind_topics,
        continue_topic=continue_topic,
        continue_session_id=continue_session_id,
        timezone=user_tz.key,
        catch_up_detail=catch_up_detail,
        due_tomorrow=due_tomorrow,
        recent_activity=recent_activity,
    )
