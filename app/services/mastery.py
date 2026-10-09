"""BKT-lite mastery + learner profile counters (Chunk 4).

Update rules (all clamped 0..1, start 0.5):
- clean advance (no probe at this idx yet): +0.15
- advance after alt (needed help): +0.08
- probe: -0.15
- escalate: -0.20
- quiz correct / wrong: +0.20 / -0.20 (Chunk 6 quiz writes call this too)

Profile counters vote: clothing of the alt that preceded an advance wins
a point; every probe votes its failure mode. Majority wins, ties keep the
current default (analogy_fun). No LLM guessing anywhere.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mastery_models import LearnerProfile, Mastery

P_INIT = 0.5
DOWN_PROBE = -0.15
DOWN_ESCALATE = -0.20

DEFAULT_CLOTHING = "analogy_fun"


def _clamp(p: float) -> float:
    return max(0.0, min(1.0, round(p, 3)))


def concept_key(topic_norm: str, idx: int) -> str:
    return f"{topic_norm}::{idx}"


async def _get_or_init_mastery(
    db: AsyncSession, user_id: uuid.UUID, key: str, label: str
) -> Mastery:
    row = (
        await db.execute(
            select(Mastery).where(
                Mastery.user_id == user_id, Mastery.concept_key == key
            )
        )
    ).scalar_one_or_none()
    if row:
        return row
    row = Mastery(user_id=user_id, concept_key=key, concept_label=label,
                  p_known=P_INIT, attempts=0)
    db.add(row)
    await db.flush()
    return row


async def observe(
    db: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    label: str,
    delta: float,
) -> Mastery:
    """Apply one evidence delta to a concept. Returns the updated row."""
    row = await _get_or_init_mastery(db, user_id, key, label)
    row.p_known = _clamp(row.p_known + delta)
    row.attempts += 1
    await db.flush()
    return row


async def set_knowledge(
    db: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    label: str,
    p_known: float,
) -> Mastery:
    """Set mastery directly from an assessment source (quiz). Quiz-gated:
    only assessed evidence may raise scores. Returns the updated row."""
    row = await _get_or_init_mastery(db, user_id, key, label)
    row.p_known = _clamp(p_known)
    row.attempts += 1
    await db.flush()
    return row


async def _get_or_init_profile(db: AsyncSession, user_id: uuid.UUID) -> LearnerProfile:
    prof = (
        await db.execute(
            select(LearnerProfile).where(LearnerProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if prof:
        return prof
    prof = LearnerProfile(user_id=user_id, clothing_wins={}, failure_counts={},
                          advances=0, probes=0, escalations=0)
    db.add(prof)
    await db.flush()
    return prof


async def count_advance(
    db: AsyncSession, user_id: uuid.UUID, helped_clothing: str | None = None
) -> LearnerProfile:
    prof = await _get_or_init_profile(db, user_id)
    prof.advances += 1
    if helped_clothing:
        wins = dict(prof.clothing_wins or {})
        wins[helped_clothing] = wins.get(helped_clothing, 0) + 1
        prof.clothing_wins = wins
    await db.flush()
    return prof


async def count_probe(db: AsyncSession, user_id: uuid.UUID, mode: str) -> LearnerProfile:
    prof = await _get_or_init_profile(db, user_id)
    prof.probes += 1
    counts = dict(prof.failure_counts or {})
    counts[mode] = counts.get(mode, 0) + 1
    prof.failure_counts = counts
    await db.flush()
    return prof


async def count_escalation(db: AsyncSession, user_id: uuid.UUID) -> LearnerProfile:
    prof = await _get_or_init_profile(db, user_id)
    prof.escalations += 1
    await db.flush()
    return prof


def _majority(counts: dict, default: str) -> str:
    if not counts:
        return default
    top = max(counts.values())
    winners = sorted(k for k, v in counts.items() if v == top)
    if default in winners:
        return default
    return winners[0]


async def profile_line(db: AsyncSession, user_id: uuid.UUID) -> str:
    """One compact line for the turn prompt. Empty when no evidence yet."""
    prof = (
        await db.execute(
            select(LearnerProfile).where(LearnerProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if prof is None or (prof.advances + prof.probes) == 0:
        return ""
    clothing = _majority(prof.clothing_wins or {}, DEFAULT_CLOTHING)
    fail = _majority(prof.failure_counts or {}, "analogy")
    weak_rows = (
        await db.execute(
            select(Mastery)
            .where(Mastery.user_id == user_id, Mastery.p_known < 0.5,
                   Mastery.attempts > 0)
            .order_by(Mastery.p_known.asc())
            .limit(3)
        )
    ).scalars().all()
    parts = [
        f"prefers {clothing}",
        f"often stuck on {fail}",
        f"{prof.advances} advances, {prof.probes} probes",
    ]
    if weak_rows:
        weak = ", ".join(f"{r.concept_label} ({r.p_known:.0%})" for r in weak_rows)
        parts.append(f"weak: {weak}")
    return "Student learning profile: " + "; ".join(parts) + "."
