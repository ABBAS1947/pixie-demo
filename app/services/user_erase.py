"""Full self-erase for compliance (workstream F).

erase_user_data(db, user) deletes every row Pixie holds for one identity,
children before parents, in one transaction — the same FK-safe order the
ops cleanup script uses, plus the tables that script misses (courses,
vault files/folders, projects, plans, usage, feedback, calendar tokens).

The script scripts/clean_test_user.py delegates here: single source of
truth for "what does Pixie store per user", which doubles as the erase
audit for the school privacy statement.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import (
    ConversationInsight,
    ConversationMessage,
    StudentFact,
    StudentProfile,
)
from app.models.lesson_models import Lesson, LessonItem, TurnEvent
from app.models.mastery_models import LearnerProfile, Mastery
from app.models.models import (
    CalendarSyncLog,
    Course,
    Deadline,
    Feedback,
    File,
    Folder,
    GoogleCalendarToken,
    Message,
    Note,
    Project,
    ProcessingJob,
    Session,
    StudyPlan,
    UsageLog,
    User,
    UserPersona,
)
from app.models.review_models import (
    Concept,
    ConceptMastery,
    Flashcard,
    MasteryHistory,
    QuizAttempt,
    QuizItem,
    QuizSession,
)


async def erase_user_data(db: AsyncSession, user: User) -> dict:
    """Delete everything stored for user. Returns counts per area."""
    uid = user.id
    counts: dict[str, int] = {}
    # Notes reference sessions without cascading; detach before removing them.
    await db.execute(Note.__table__.update().where(Note.user_id == uid).values(session_id=None))

    # Shared learning: invalidate jobs and remove private evidence in the same erase transaction.
    installed = (await db.execute(text("SELECT to_regclass('learning_activities') IS NOT NULL"))).scalar()
    if installed:
        anchors = (await db.execute(text('SELECT DISTINCT item_id FROM learning_tasks WHERE user_id=:user'), {'user': uid})).scalars().all()
        await db.execute(text("SELECT id FROM learning_activities WHERE user_id=:user FOR UPDATE"), {"user": uid})
        await db.execute(text("DELETE FROM learning_jobs WHERE event_id IN (SELECT id FROM learning_evidence WHERE user_id=:user)"), {"user": uid})
        await db.execute(text("UPDATE learning_tasks SET prior_event_id=NULL WHERE user_id=:user"), {"user": uid})
        await db.execute(text("DELETE FROM learning_evidence WHERE user_id=:user"), {"user": uid})
        await db.execute(text("DELETE FROM learning_submissions WHERE activity_id IN (SELECT id FROM learning_activities WHERE user_id=:user)"), {"user": uid})
        await db.execute(text("UPDATE learning_activities SET task_id=NULL WHERE user_id=:user"), {"user": uid})
        for table in ("learning_tasks", "learning_starts", "learning_summaries", "learning_activities"):
            await db.execute(text(f"DELETE FROM {table} WHERE user_id=:user"), {"user": uid})
        counts["shared_learning"] = 1
        for anchor in anchors:
            await db.execute(text('DELETE FROM learning_items WHERE id=:id AND reserved AND NOT EXISTS(SELECT 1 FROM learning_tasks WHERE item_id=:id)'), {'id': anchor})

    # New Review children and source mappings must not outlive their owner.
    if (await db.execute(text("SELECT to_regclass('review_preparation_jobs') IS NOT NULL"))).scalar():
        for table in ('review_item_reports', 'review_request_results', 'review_xp_events', 'review_preparation_jobs'):
            column = 'quiz_id'
            await db.execute(text(f'DELETE FROM {table} WHERE {column} IN (SELECT id FROM quiz_sessions WHERE user_id=:user)'), {'user': uid})
    if installed:
        await db.execute(text("DELETE FROM learning_skill_mappings WHERE source_type='review_concept' AND source_id IN (SELECT id FROM concepts WHERE user_id=:user)"), {'user': uid})

    # Core deletes do not decrypt content. Cleanup remains possible after a
    # key outage/loss and never requires loading learner plaintext into memory.
    lesson_ids = select(Lesson.id).where(Lesson.user_id == uid)
    quiz_ids = select(QuizSession.id).where(QuizSession.user_id == uid)
    for model, predicate in (
        (LessonItem, LessonItem.lesson_id.in_(lesson_ids)),
        (TurnEvent, TurnEvent.lesson_id.in_(lesson_ids)),
        (Lesson, Lesson.user_id == uid),
        (QuizAttempt, QuizAttempt.user_id == uid),
        (QuizItem, QuizItem.quiz_session_id.in_(quiz_ids)),
        (QuizSession, QuizSession.user_id == uid),
    ):
        result = await db.execute(model.__table__.delete().where(predicate))
        counts[model.__tablename__] = result.rowcount
    # Child-first order also covers explicit FKs not represented by ORM relations.
    for model in (
        StudentFact, Message, ConversationMessage, ConversationInsight, Session,
        Flashcard, MasteryHistory, ConceptMastery, Concept, ProcessingJob,
        StudyPlan, Project, Mastery, Deadline, File, Note, Course, Folder,
        UsageLog, GoogleCalendarToken, CalendarSyncLog, Feedback,
        LearnerProfile, StudentProfile, UserPersona,
    ):
        result = await db.execute(model.__table__.delete().where(model.user_id == uid))
        counts[model.__tablename__] = result.rowcount
    result = await db.execute(User.__table__.delete().where(User.id == uid))
    counts["user"] = result.rowcount
    # File/provider cleanup belongs to the durable deletion worker, never an
    # unvalidated user.vault_path or an ignored filesystem failure.
    return counts
