"""Lazy concept extraction from notes with embedding-based dedup.

When a note is first reviewed, concepts are extracted via LLM, embedded
with Ollama (embeddinggemma, 768d), and deduplicated against existing
concepts using pgvector cosine similarity (threshold 0.92).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Note
from app.models.review_models import Concept, ConceptMastery
from app.services.llm_client import llm_json
from app.services.ollama_client import embed_text


async def _extract_concepts_via_llm(note: Note) -> list[dict]:
    """Ask the LLM to extract discrete learning concepts from a note.

    Returns a list of {"label": "..."} dicts.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You extract discrete learning concepts from study notes. "
                "Return a JSON object with a single key 'concepts' containing "
                "a list of objects, each with a 'label' field (short, 3-15 words). "
                "Focus on testable knowledge: definitions, formulas, processes, "
                "relationships. Ignore structural elements like 'introduction' or 'summary'."
            ),
        },
        {
            "role": "user",
            "content": f"Title: {note.title}\n\nContent:\n{note.content[:4000]}",
        },
    ]
    result = await llm_json(messages, max_tokens=1024)
    concepts = result.get("concepts", [])
    # Normalize to list of label strings
    return [{"label": c["label"]} for c in concepts if "label" in c]


async def find_similar_concept(
    session: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID | None,
    embedding: list[float],
    threshold: float = 0.92,
) -> Concept | None:
    """pgvector cosine search for an existing concept close to the given embedding.

    Returns the most similar concept above the threshold, or None.
    """
    # Build the cosine distance expression: 1 - (embedding <=> query)
    from sqlalchemy import text

    query = (
        select(Concept)
        .where(Concept.user_id == user_id)
        .where(Concept.embedding.cosine_distance(embedding) < (1 - threshold))
        .order_by(Concept.embedding.cosine_distance(embedding))
        .limit(1)
    )
    if course_id is not None:
        query = query.where(Concept.course_id == course_id)

    result = await session.execute(query)
    return result.scalar_one_or_none()


async def ensure_concepts_for_note(
    session: AsyncSession,
    user_id: uuid.UUID,
    note: Note,
    course_id: uuid.UUID | None = None,
) -> list[Concept]:
    """Extract concepts for a note if not already done; deduplicate by embedding.

    Returns the list of Concept objects associated with this note (including
    ones that were deduped to existing concepts).
    """
    # Check if concepts already exist for this note
    existing = (
        await session.execute(
            select(Concept).where(
                Concept.user_id == user_id,
                Concept.source_note_id == note.id,
            )
        )
    ).scalars().all()
    if existing:
        return list(existing)

    # Extract concepts via LLM
    raw_concepts = await _extract_concepts_via_llm(note)
    if not raw_concepts:
        return []

    created_concepts: list[Concept] = []

    for raw in raw_concepts:
        label = raw["label"]
        embedding = await embed_text(label)

        # Check for similar existing concept (dedup)
        similar = await find_similar_concept(
            session, user_id, course_id, embedding
        )

        if similar:
            # Concept already exists — link via mastery but don't create duplicate
            # Ensure mastery record exists
            mastery = (
                await session.execute(
                    select(ConceptMastery).where(
                        ConceptMastery.user_id == user_id,
                        ConceptMastery.concept_id == similar.id,
                    )
                )
            ).scalar_one_or_none()
            if not mastery:
                mastery = ConceptMastery(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    concept_id=similar.id,
                    confidence=0.5,
                    signal_count=0,
                    introduced_at=datetime.now(timezone.utc),
                )
                session.add(mastery)
            created_concepts.append(similar)
        else:
            # New concept — create it
            concept = Concept(
                id=uuid.uuid4(),
                user_id=user_id,
                course_id=course_id,
                label=label,
                embedding=embedding,
                source_note_id=note.id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(concept)
            await session.flush()  # Get the ID

            # Register one deterministic cross-surface identity. Publication
            # stays proposed until source-grounded items pass review; labels
            # never create a second skill or silently merge existing mastery.
            shared_ready = (await session.execute(
                text("SELECT to_regclass('learning_skill_mappings') IS NOT NULL")
            )).scalar()
            if shared_ready:
                code = f"review:concept:{concept.id}"
                await session.execute(text("""
                    INSERT INTO learning_skills(code,version,objective,published,approval)
                    VALUES(:code,1,:objective,false,NULL)
                    ON CONFLICT(code,version) DO NOTHING
                """), {"code": code, "objective": concept.label[:1000]})
                await session.execute(text("""
                    INSERT INTO learning_skill_mappings
                      (id,source_type,source_id,skill_code,skill_version,status,rationale)
                    VALUES(:id,'review_concept',:source,:code,1,'proposed',:rationale)
                    ON CONFLICT(source_type,source_id) DO NOTHING
                """), {"id": uuid.uuid4(), "source": concept.id, "code": code,
                       "rationale": "Concept extracted from an owned study note; pending grounded item review."})

            # Create mastery record
            mastery = ConceptMastery(
                id=uuid.uuid4(),
                user_id=user_id,
                concept_id=concept.id,
                confidence=0.5,
                signal_count=0,
                introduced_at=datetime.now(timezone.utc),
            )
            session.add(mastery)
            created_concepts.append(concept)

    await session.commit()
    return created_concepts
