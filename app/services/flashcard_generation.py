"""Flashcard generation with coverage caching.

Generates flashcards for concepts on demand. Ensures every concept has
at least 3 flashcards (mix of MCQ and short_answer). Generated cards are
cached in the database — subsequent calls return existing cards.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_models import Concept, Flashcard
from app.models.models import Note
from app.services.llm_client import llm_json
from app.services.untrusted_document import DOCUMENT_GUARD, untrusted_document_text


async def _count_flashcards(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> int:
    """Count existing flashcards for a concept."""
    result = await session.execute(
        select(func.count()).select_from(Flashcard).where(
            Flashcard.user_id == user_id,
            Flashcard.concept_id == concept_id,
            Flashcard.review_content.is_(None),
            Flashcard.format.in_(['mcq','short_answer']),
        )
    )
    return result.scalar() or 0


async def _generate_flashcards_via_llm(concept_label: str, source_text: str) -> list[dict]:
    """Ask the LLM to generate flashcards for a concept.

    Returns a list of card dicts with format, question, answer, and options.
    """
    messages = [
        {
            "role": "system",
            "content": (
                f"{DOCUMENT_GUARD} You generate flashcards for studying. For each concept, create "
                "exactly 2 cards: one multiple-choice question (MCQ) and one "
                "short-answer question. Return a JSON object with a 'cards' key "
                "containing a list of objects, each with:\n"
                "- 'format': 'mcq' or 'short_answer'\n"
                "- 'question': the question text\n"
                "- 'answer': the correct answer\n"
                "- 'options': list of 4 option strings (MCQ only, null for short_answer)\n\n"
                "Make questions specific and testable from the supplied source. "
                "Test understanding, relationships, definitions, decisions, or "
                "procedures. Do not ask about page counts, issue dates, filenames, "
                "authors, or other document metadata unless that metadata is the "
                "explicit concept. Distractors for MCQ should be plausible but "
                "clearly wrong. Never invent facts absent from the source."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Concept: {concept_label}\n\n"
                f"{untrusted_document_text(source_text, limit=12000)}"
            ),
        },
    ]
    result = await llm_json(messages, max_tokens=1024)
    return result.get("cards", [])


async def ensure_flashcard_coverage(
    session: AsyncSession,
    user_id: uuid.UUID,
    concept: Concept,
    min_cards: int = 3,
) -> list[Flashcard]:
    """Ensure a concept has at least ``min_cards`` flashcards.

    If fewer exist, generates more via LLM until the minimum is met.
    Returns all flashcards for the concept (existing + newly created).
    """
    # Get existing cards
    existing = (
        await session.execute(
            select(Flashcard).where(
                Flashcard.user_id == user_id,
                Flashcard.concept_id == concept.id,
                Flashcard.review_content.is_(None),
                Flashcard.format.in_(['mcq','short_answer']),
            )
        )
    ).scalars().all()

    if len(existing) >= min_cards:
        return list(existing)

    # Ground generation in the owning note. A concept without source material
    # is not eligible for a new card; this prevents label-only trivia.
    source_text = ""
    if concept.source_note_id is not None:
        source = (await session.execute(select(Note).where(
            Note.id == concept.source_note_id, Note.user_id == user_id
        ))).scalar_one_or_none()
        source_text = source.content if source else ""
    if not source_text.strip():
        return list(existing)
    generated = await _generate_flashcards_via_llm(concept.label, source_text)

    for card_data in generated:
        fmt = card_data.get("format", "short_answer")
        if fmt not in ("mcq", "short_answer"):
            fmt = "short_answer"
        question = str(card_data.get("question", "")).strip()
        answer = str(card_data.get("answer", "")).strip()
        if not question or not answer:
            continue

        card = Flashcard(
            id=uuid.uuid4(),
            user_id=user_id,
            concept_id=concept.id,
            note_id=concept.source_note_id,
            format=fmt,
            question=question,
            answer=answer,
            options=card_data.get("options") if fmt == "mcq" else None,
            created_at=datetime.now(timezone.utc),
        )
        session.add(card)
        existing.append(card)

        if len(existing) >= min_cards:
            break

    await session.flush()
    await session.commit()
    return list(existing)
