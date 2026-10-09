"""Fact Extraction Service — extracts discrete student facts from conversations.

After each session, analyzes the transcript and compares against existing facts
to find NEW facts, REINFORCED facts, and CONTRADICTED facts. Updates the
student_facts table accordingly.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import StudentFact
from app.models.models import Message
from app.services.llm_registry import get_provider

logger = logging.getLogger(__name__)

# Context-type facts expire after 7 days
CONTEXT_EXPIRY_DAYS = 7

FACT_EXTRACTION_PROMPT = """You are analyzing a tutoring conversation to extract structured facts about the student.

EXISTING FACTS (already known about this student):
{existing_facts_json}

CONVERSATION TRANSCRIPT:
{transcript}

Extract facts about the student as a JSON array. Each fact:
{{
  "type": "preference|confusion|strength|weakness|pattern|milestone|context",
  "category": "subject area or learning_style or behavior or general",
  "content": "Clear, specific fact about the student (e.g. 'Prefers visual explanations over text')",
  "action": "new|reinforce|contradict",
  "related_fact_id": "id of existing fact if reinforcing/contradicting, null for new"
}}

Rules:
- Extract facts that reveal HOW the student learns, WHAT they struggle with, WHAT they're good at
- "preference": learning style preferences (visual, verbal, hands-on, etc.)
- "confusion": topics or concepts the student is confused about
- "strength": topics the student understands well
- "weakness": topics where the student needs improvement
- "pattern": behavioral patterns (e.g. "asks many questions when anxious")
- "milestone": achievements or breakthroughs (e.g. "Finally understood mitosis")
- "context": temporary context (e.g. "Has a biology exam tomorrow")
- For reinforce: match to an existing fact's id and action="reinforce"
- For contradict: match to an existing fact's id and action="contradict" (new evidence weakens it)
- Return ONLY the JSON array, no other text
- If no facts can be extracted, return an empty array: []
"""


def _build_conversation_text(messages: list[Message], max_chars: int = 10000) -> str:
    """Flatten messages into a readable transcript for the LLM."""
    parts = []
    total = 0
    for m in messages:
        role = "Student" if m.role == "user" else "Pixie"
        chunk = f"{role}: {m.content}\n"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts)


async def _get_existing_facts(
    db: AsyncSession, user_id: uuid.UUID
) -> list[StudentFact]:
    """Fetch all active, non-expired facts for the user."""
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
    )
    return list(result.scalars().all())


async def extract_facts(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    """Extract facts from a session and update the fact store.

    Returns the number of facts created/updated.
    Best-effort: catches all exceptions, logs them, never raises.
    """
    try:
        # Fetch messages for this session
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        messages = list(result.scalars().all())

        if len(messages) < 2:
            logger.info("Session %s has fewer than 2 messages, skipping fact extraction", session_id)
            return 0

        transcript = _build_conversation_text(messages)
        if not transcript.strip():
            return 0

        # Fetch existing facts
        existing_facts = await _get_existing_facts(db, user_id)

        # Build existing facts JSON for the LLM
        existing_facts_json = json.dumps(
            [
                {
                    "id": str(f.id),
                    "type": f.fact_type,
                    "category": f.category,
                    "content": f.content,
                    "confidence": f.confidence,
                    "mention_count": f.mention_count,
                }
                for f in existing_facts
            ],
            indent=2,
        ) if existing_facts else "[]"

        # LLM extraction
        provider = get_provider("extraction")
        prompt = FACT_EXTRACTION_PROMPT.format(
            existing_facts_json=existing_facts_json,
            transcript=transcript,
        )

        result = await provider.complete(
            [
                {"role": "system", "content": "You are a fact extraction assistant. Reply ONLY with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
            temperature=0,
        )

        extracted_facts = json.loads(result["content"])
        if not isinstance(extracted_facts, list):
            logger.warning("Fact extraction returned non-list for session %s", session_id)
            return 0

        now = datetime.now(timezone.utc)
        fact_count = 0

        # Build lookup for existing facts by ID
        fact_lookup = {str(f.id): f for f in existing_facts}

        for fact_data in extracted_facts:
            action = fact_data.get("action", "new")
            related_id = fact_data.get("related_fact_id")

            if action == "reinforce" and related_id and related_id in fact_lookup:
                # Reinforce existing fact
                fact = fact_lookup[related_id]
                fact.confidence = min(1.0, fact.confidence + 0.1)
                fact.mention_count += 1
                fact.last_seen = now
                fact_count += 1
                logger.debug("Reinforced fact %s: confidence=%.2f", related_id, fact.confidence)

            elif action == "contradict" and related_id and related_id in fact_lookup:
                # Contradict existing fact
                fact = fact_lookup[related_id]
                fact.confidence = max(0.0, fact.confidence - 0.2)
                fact.last_seen = now
                fact_count += 1
                logger.debug("Contradicted fact %s: confidence=%.2f", related_id, fact.confidence)

            elif action == "new":
                # Create new fact
                fact_type = fact_data.get("type", "context")
                category = fact_data.get("category", "general")
                content = fact_data.get("content", "").strip()
                if not content:
                    continue

                new_fact = StudentFact(
                    user_id=user_id,
                    fact_type=fact_type,
                    category=category,
                    content=content,
                    confidence=0.5,
                    mention_count=1,
                    first_seen=now,
                    last_seen=now,
                    source_session_id=session_id,
                    is_active=True,
                    # Context-type facts expire after 7 days
                    expires_at=(now + timedelta(days=CONTEXT_EXPIRY_DAYS))
                    if fact_type == "context"
                    else None,
                )
                db.add(new_fact)
                fact_count += 1
                logger.debug("Created new fact: type=%s, content=%s", fact_type, content[:80])

        if fact_count > 0:
            await db.flush()
            logger.info(
                "Extracted %d facts for user %s from session %s",
                fact_count,
                user_id,
                session_id,
            )

        return fact_count

    except Exception as e:
        logger.warning(
            "Fact extraction failed for session %s (user %s): %s",
            session_id,
            user_id,
            e,
            exc_info=True,
        )
        return 0
