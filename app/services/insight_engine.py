"""Insight Extraction Engine — three-phase pipeline.

Phase 1 (Classify): identify subject and topics from the conversation.
Phase 2 (Extract): structured extraction of difficulty signals, concepts, tools.
Phase 3 (Reduce): summarize and assess mood/sentiment.

Each phase uses the LLM provider abstraction (llm_registry).
The engine is designed to be called from a background task (never blocks chat).
"""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_models import ConversationInsight
from app.models.models import Message, Session
from app.services.llm_registry import get_provider

logger = logging.getLogger(__name__)


def _build_conversation_text(messages: list[Message], max_chars: int = 12000) -> str:
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


async def _phase_classify(transcript: str) -> dict:
    """Phase 1: classify subject and topics."""
    provider = get_provider("classification")
    result = await provider.complete(
        [
            {
                "role": "system",
                "content": (
                    "You are an academic conversation classifier. "
                    "Analyze the student-tutor conversation and identify the academic subject(s) and topics discussed.\n"
                    "Reply ONLY with JSON:\n"
                    '{"subjects": ["Biology"], "topics": ["mitosis", "cell division", "prophase"]}\n'
                    "Use lowercase topic names. Be specific (e.g. 'cell division' not just 'biology')."
                ),
            },
            {"role": "user", "content": transcript},
        ],
        json_mode=True,
        temperature=0,
    )
    try:
        return json.loads(result["content"])
    except (json.JSONDecodeError, ValueError):
        return {"subjects": [], "topics": []}


async def _phase_extract(transcript: str) -> dict:
    """Phase 2: extract difficulty signals, concepts, tools, questions."""
    provider = get_provider("extraction")
    result = await provider.complete(
        [
            {
                "role": "system",
                "content": (
                    "You are an educational conversation analyst. "
                    "Extract structured data from this student-tutor conversation.\n"
                    "Reply ONLY with JSON:\n"
                    "{\n"
                    '  "concepts_covered": ["prophase", "metaphase", "anaphase"],\n'
                    '  "difficulty_signals": [{"topic": "anaphase", "signal": "confused"}, {"topic": "cytokinesis", "signal": "struggled"}],\n'
                    '  "tools_used": ["create_note", "search_notes"],\n'
                    '  "questions_asked": 3,\n'
                    '  "concepts_explained": 5\n'
                    "}\n\n"
                    "difficulty_signals: list signals where the student showed confusion, "
                    "struggle, or incorrect understanding. signal can be: confused, struggled, "
                    "incorrect_answer, asked_repetition, or confident.\n"
                    "tools_used: list any study tools used (create_note, search_notes, list_notes, "
                    "read_note, list_files, read_file, create_deadline, list_deadlines, etc.).\n"
                    "questions_asked: number of distinct questions the student asked.\n"
                    "concepts_explained: number of distinct concepts the tutor explained."
                ),
            },
            {"role": "user", "content": transcript},
        ],
        json_mode=True,
        temperature=0,
    )
    try:
        return json.loads(result["content"])
    except (json.JSONDecodeError, ValueError):
        return {
            "concepts_covered": [],
            "difficulty_signals": [],
            "tools_used": [],
            "questions_asked": 0,
            "concepts_explained": 0,
        }


async def _phase_reduce(transcript: str) -> dict:
    """Phase 3: summarize and assess mood/sentiment."""
    provider = get_provider("summarization")
    result = await provider.complete(
        [
            {
                "role": "system",
                "content": (
                    "You are an educational conversation summarizer. "
                    "Summarize this student-tutor conversation in 2-3 sentences, "
                    "then assess the student's mood and sentiment.\n"
                    "Reply ONLY with JSON:\n"
                    "{\n"
                    '  "summary": "Student reviewed mitosis phases, struggled with anaphase, practiced with quiz.",\n'
                    '  "mood": "engaged",\n'
                    '  "sentiment_score": 0.6\n'
                    "}\n\n"
                    "mood must be one of: engaged, confused, frustrated, confident, neutral.\n"
                    "sentiment_score: float from -1.0 (very negative) to 1.0 (very positive). "
                    "0.0 is neutral. Consider the student's tone, questions, and understanding."
                ),
            },
            {"role": "user", "content": transcript},
        ],
        json_mode=True,
        temperature=0,
    )
    try:
        return json.loads(result["content"])
    except (json.JSONDecodeError, ValueError):
        return {"summary": "", "mood": "neutral", "sentiment_score": 0.0}


async def extract_insight(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ConversationInsight | None:
    """Run the full three-phase insight extraction pipeline.

    Returns a ConversationInsight object (not yet persisted).
    Returns None if the session has too few messages for meaningful analysis.
    """
    # Fetch all messages for this session
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = list(result.scalars().all())

    # Need at least 2 messages (1 user + 1 assistant) for analysis
    if len(messages) < 2:
        logger.info("Session %s has fewer than 2 messages, skipping insight extraction", session_id)
        return None

    transcript = _build_conversation_text(messages)
    if not transcript.strip():
        return None

    # Run all three phases (best-effort: if one fails, use defaults)
    try:
        classify = await _phase_classify(transcript)
    except Exception as e:
        logger.warning("Phase classify failed for session %s: %s", session_id, e)
        classify = {"subjects": [], "topics": []}

    try:
        extract = await _phase_extract(transcript)
    except Exception as e:
        logger.warning("Phase extract failed for session %s: %s", session_id, e)
        extract = {
            "concepts_covered": [],
            "difficulty_signals": [],
            "tools_used": [],
            "questions_asked": 0,
            "concepts_explained": 0,
        }

    try:
        reduce_ = await _phase_reduce(transcript)
    except Exception as e:
        logger.warning("Phase reduce failed for session %s: %s", session_id, e)
        reduce_ = {"summary": "", "mood": "neutral", "sentiment_score": 0.0}

    # Build the insight object
    insight = ConversationInsight(
        session_id=session_id,
        user_id=user_id,
        topics=classify.get("topics", []),
        subjects=classify.get("subjects", []),
        concepts_covered=extract.get("concepts_covered", []),
        difficulty_signals=extract.get("difficulty_signals", []),
        tools_used=extract.get("tools_used", []),
        questions_asked=extract.get("questions_asked", 0),
        concepts_explained=extract.get("concepts_explained", 0),
        mood=reduce_.get("mood", "neutral"),
        summary=reduce_.get("summary", ""),
        sentiment_score=reduce_.get("sentiment_score", 0.0),
    )

    return insight
