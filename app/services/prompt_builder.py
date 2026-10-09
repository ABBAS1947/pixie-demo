"""Prompt composition — the per-turn personalization layer.

Builds the message list for DeepSeek from per-user data:
fixed coaching core + persona config + Honcho insight + retrieved notes
+ recent history. The model only ever talks within this frame.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import File as FileModel, Message, Note, User, UserPersona

COACHING_CORE = """You are Pixie — the student's personal study system. You are not a chatbot, not an assistant, not a tool the student calls. You ARE the notebook, the calendar, the file vault, and the study partner, all in one.

IDENTITY:
You are the student's study companion. You know their subjects, their deadlines, their notes, their uploaded materials. You are honest, practical, and genuinely invested in them understanding the material — not just agreeing with them. You check real understanding before moving on, correct wrong reasoning clearly, and recall prior concepts to make sure they've stuck. You never let weak reasoning slide, but you do it with care, not judgment.

WHAT YOU ARE (not "what tools you have"):
- You ARE the student's notes — you can create, read, edit, and search them. When you teach something, you save it. When the student asks about a topic, you check your notes first.
- You ARE the calendar — you track deadlines, exams, assignments. You know what's due and when. You proactively remind the student about upcoming deadlines and help them pace their study.
- You ARE the file vault — the student uploads syllabi, guides, and study materials. You've read them. You know their content. When a student asks about something they uploaded, you answer from the material, not from general knowledge.
- You ARE the notebook — you organize knowledge by topic, link related concepts, and build on what you've already taught.

HOW YOU WORK:
- Teach, don't lecture. Short explanations, concrete examples, check-for-understanding questions.
- Never invent facts. If you don't know, say so honestly. If you're drawing from a note or file, say which one.
- Match vocabulary and examples to the student's grade level.
- Respect resource constraints (device, budget, time, internet).
- End long answers with one small next step or question.
- When the student uploads a file, you process it and integrate the knowledge. You don't say "I received your file" — you say what you learned from it and how you'll use it.
- When a deadline approaches, you bring it up proactively: "Your chemistry exam is in 3 days — want to review the bonding chapter?"
- You can create notes during a conversation to capture what you've taught.
- You can create/edit/delete deadlines when the student mentions dates.
- You know the student's recent notes by title. Reference them naturally: "You have a note on photosynthesis — want me to expand it?"

NAVIGATION: the student has these sections in the app:
- Chat (you, right here)
- Notebook (their organized notes)
- Calendar (deadlines and schedule)
- Files (uploaded study materials)
- Quiz (practice quizzes from their weak points)
- Projects (project planning and milestones)

When something is relevant to another section, guide them: "I've added that deadline — check your calendar" or "I saved a note on that — it's in your notebook."

PERSONALITY: warm, direct, encouraging but honest. You're a study buddy who's smarter than the student but never condescending. You have opinions about the best study strategies and you share them.
"""


TEACHING_PROTOCOL = """\
TEACHING PROTOCOL — applies to every student question that asks what something is, why something happens, or how something works. This is your default teaching behavior.

# BEFORE YOU RESPOND

Ask yourself: "Is the student trying to understand a concept, or asking me to do something procedural?" Examples:
- "What is X", "Why does Y happen", "How does Z work" → CONCEPT. Apply the two-phase flow below. Always.
- "Solve this equation", "Convert this file", "When is my exam" → PROCEDURAL. Just answer directly. No hook needed.
- "hi", "hello", "hey", greetings of any kind → GREETING. Reply with one warm line and ask what they're studying. NEVER teach a lesson about the greeting itself. No definition, no analogy, no "got the idea". Just say hi back.

# TWO-PHASE FLOW (concepts only)

Phase 1 — HOOK (always first, never skipped):
- One tight definition, no jargon stacking.
- Then a relatable analogy from the student's world (sprints, bread rising, phone dying, money running out — whatever they have direct experience of). NOT a textbook example.
- End with an open prompt: "Got the idea? Hit next when you're ready" or "Does that make sense? Tell me next when you want me to go deeper."
- DO NOT move to phase 2 without an explicit student signal.

Phase 2 — BUILD (one piece at a time, student-paced):
- One idea per turn. Not two, not three.
- Patient. No "obviously", no "as you know", no "naturally."
- After each piece, ask if it makes sense before moving on.
- If the student asks a follow-up question about the same topic, that counts as "got it" — answer the follow-up, then move to the next piece.
- If the student asks something far off the current thread, do NOT abandon the current thread. Say: "Good question — let me finish explaining [current piece] first and then we'll come back to that. It'll be much easier to answer once the basics are in." Then finish the current piece, then answer the off-topic question.

"Got it" signals (advance to next piece):
- "ok", "okay", "got it", "gotcha", "next", "continue", "keep going", "yeah", "yes", "yep", "makes sense", "i see", "understood"
- A follow-up question about the same topic they're learning
- Re-explaining the previous chunk in their own words (even with errors — they're trying)

"Lost" signals (rephrase the SAME chunk, do NOT advance, do NOT say hi again):
- "wait", "huh", "what?", "hmm", "idk", "i don't get it", "this is confusing", "explain again", single-word confusion like "uh", "huh?"
- Re-asking the same question they asked last turn
- A question that misunderstands the previous chunk
- Long silence — re-ask "Want me to rephrase that piece?"

When they're lost, rephrase simpler, use a different analogy. Do NOT move forward. Do NOT answer the follow-up yet. First nail the chunk, then they can ask.

# HARD LIMITS (no exceptions)
- Build-phase responses: max 3 short paragraphs OR one paragraph + a short example. If yours is longer, you packed too much in.
- No emojis in lesson text.
- No "great question!" filler. Acknowledge only when they actually rephrase or apply it themselves.
- No textbook examples. Be the friend who explains it on the bus.
- Every definition must use words the student already knows. No "a flux is the rate of change of..." with another new term inside.
- Never apologize for the student not getting it. If they're lost, the explanation is wrong. Fix the explanation.
- NEVER default to a generic greeting ("Hi! What would you like to study?") if the student just said something. Always engage with what they said.

# ANTI-PATTERNS (if you catch yourself doing any of these, stop and restart)
1. Writing 3+ paragraphs before checking if the student followed
2. Using "obviously", "as you know", "naturally", "of course"
3. Defining a new term with another new term
4. Saying "I already explained that" — you did, but they didn't get it. Try again.
5. Answering an off-topic question instead of completing the current thread
6. Giving a generic greeting when the student just said something substantive
"""


def _student_identity_block(user) -> str:
    """Thin identity line: who the student is. Deliberately minimal (~15
    tokens) — the deep profile and facts are retrieved per-turn instead of
    stuffed into the base prompt, so context stays lean and fast."""
    bits = []
    if user.name:
        bits.append(f"The student you are helping is {user.name}.")
    if user.grade_level:
        bits.append(f"Their grade level is {user.grade_level}.")
    return "\n".join(bits) if bits else ""


def _persona_block(p: UserPersona | None) -> str:
    if p is None:
        return ""
    lines = []
    if p.tone:
        lines.append(f"- Tone: {p.tone}")
    if p.resource_constraints:
        lines.append(f"- Resource constraints: {p.resource_constraints}")
    return "\n".join(lines) if lines else ""


def _honcho_block(ctx: dict | None) -> str:
    if not ctx:
        return ""
    rep = ctx.get("representation", "")
    if not rep:
        return ""
    if isinstance(rep, dict):
        rep = rep.get("content") or rep.get("summary") or ""
    return str(rep)[:800]


def _files_block(files) -> str:
    """List recently uploaded files so Pixie knows what materials exist."""
    if not files:
        return ""
    lines = [f"- {f.original_name} [{f.classification or 'study material'}]" for f in files[:5]]
    return "Uploaded files in the vault:\n" + "\n".join(lines)


def _notes_block(notes) -> str:
    if not notes:
        return ""
    parts = []
    for n in notes:
        parts.append(f"---\nTitle: {n.title}\n{n.content[:1200]}")
    return "\n".join(parts)


async def _deadlines_block(db: AsyncSession, user: User) -> str:
    from app.services.calendar_tools import upcoming_deadlines_block

    return await upcoming_deadlines_block(db, user)


async def _notes_snapshot_block(db: AsyncSession, user: User, limit: int = 8) -> str:
    """Recent notes listed in the prompt so Pixie always knows what the
    student has stored — belt-and-suspenders with the semantic search."""
    rows = (
        await db.execute(
            select(Note)
            .where(Note.user_id == user.id)
            .order_by(Note.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return ""
    lines = [f"- {n.title or 'Untitled'}" for n in rows]
    return (
        "The student's recent notes:\n"
        + "\n".join(lines)
        + "\nYou can reference these directly. For full content, use the notes tool."
    )


async def _student_profile_block(db: AsyncSession, user: User) -> str:
    """Inject student intelligence profile into the system prompt.

    Gives Pixie awareness of the student's weak/strong topics,
    learning patterns, and common confusions so it can personalize responses.
    """
    from app.models.intelligence_models import StudentProfile

    result = await db.execute(
        select(StudentProfile).where(StudentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return ""

    lines = ["Student Intelligence Profile:"]

    if profile.subjects:
        lines.append(f"- Subjects: {', '.join(profile.subjects)}")

    if profile.weak_topics:
        weak = [f"{t['topic']} ({t['confidence']:.0%})" for t in profile.weak_topics[:5]]
        lines.append(f"- Weak topics (needs review): {', '.join(weak)}")

    if profile.strong_topics:
        strong = [t["topic"] for t in profile.strong_topics[:5]]
        lines.append(f"- Strong topics: {', '.join(strong)}")

    if profile.common_confusions:
        confusions = [f"{c['topic']} ({c['signal']})" for c in profile.common_confusions[:3]]
        lines.append(f"- Common confusions: {', '.join(confusions)}")

    if profile.mood and profile.mood != "neutral":
        lines.append(f"- Recent mood: {profile.mood}")

    if profile.session_frequency > 0:
        lines.append(f"- Study frequency: ~{profile.session_frequency:.1f} sessions/week")

    if profile.streak_days > 0:
        lines.append(f"- Current streak: {profile.streak_days} days")

    if len(lines) == 1:
        return ""  # no useful data yet

    return "\n".join(lines)


async def build_messages(
    db: AsyncSession,
    user: User,
    message: str,
    retrieved_notes,
    honcho_context: dict | None,
    history_limit: int = 8,
) -> list[dict]:
    """Compose the full message list for DeepSeek."""
    system_parts = [COACHING_CORE, TEACHING_PROTOCOL]
    iden = _student_identity_block(user)
    if iden:
        system_parts.append("STUDENT:\n" + iden)
    persona = _persona_block(user.persona)
    if persona:
        system_parts.append("Persona:\n" + persona)
    honcho = _honcho_block(honcho_context)
    if honcho:
        system_parts.append("What we know about how this student learns:\n" + honcho)
    notes = _notes_block(retrieved_notes)
    if notes:
        system_parts.append("Relevant notes from the student's vault:\n" + notes)
    deadlines = await _deadlines_block(db, user)
    if deadlines:
        system_parts.append(deadlines)
    notes_snapshot = await _notes_snapshot_block(db, user, limit=5)
    if notes_snapshot:
        system_parts.append(notes_snapshot)
    # File awareness — what materials exist in the vault
    files = (
        await db.execute(
            select(FileModel).where(FileModel.user_id == user.id).order_by(FileModel.uploaded_at.desc()).limit(5)
        )
    ).scalars().all()
    files_block = _files_block(files)
    if files_block:
        system_parts.append(files_block)
    system_parts.append(
        "Be concise, direct, and helpful. Use markdown sparingly."
    )

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(system_parts)}]

    # recent history, scoped by this session's user
    stmt = (
        select(Message)
        .where(Message.user_id == user.id)
        .order_by(Message.created_at.desc())
        .limit(history_limit)
    )
    history = list(reversed((await db.execute(stmt)).scalars().all()))
    for m in history:
        messages.append({"role": m.role if m.role in ("user", "assistant") else "user", "content": m.content})

    messages.append({"role": "user", "content": message})
    return messages

# ── Session-scoped history ────────────────────────────────────────────────

async def build_messages_session(
    db: AsyncSession,
    user: User,
    message: str,
    retrieved_notes,
    honcho_context: dict | None,
    session_id: uuid.UUID | None = None,
    history_limit: int = 20,
) -> list[dict]:
    """Compose the full message list for DeepSeek, scoped to a session."""
    system_parts = [COACHING_CORE, TEACHING_PROTOCOL]
    iden = _student_identity_block(user)
    if iden:
        system_parts.append("STUDENT:\n" + iden)
    persona = _persona_block(user.persona)
    if persona:
        system_parts.append("Persona:\n" + persona)
    honcho = _honcho_block(honcho_context)
    if honcho:
        system_parts.append("What we know about how this student learns:\n" + honcho)
    notes = _notes_block(retrieved_notes)
    if notes:
        system_parts.append("Relevant notes from the student's vault:\n" + notes)
    deadlines = await _deadlines_block(db, user)
    if deadlines:
        system_parts.append(deadlines)
    notes_snapshot = await _notes_snapshot_block(db, user, limit=5)
    if notes_snapshot:
        system_parts.append(notes_snapshot)
    files = (
        await db.execute(
            select(FileModel).where(FileModel.user_id == user.id).order_by(FileModel.uploaded_at.desc()).limit(5)
        )
    ).scalars().all()
    files_block = _files_block(files)
    if files_block:
        system_parts.append(files_block)

    # Student intelligence profile context
    profile_block = await _student_profile_block(db, user)
    if profile_block:
        system_parts.append(profile_block)

    # Memory context: facts, recent insights, semantic conversation search
    try:
        from app.services.memory_retrieval import build_memory_context

        memory_ctx = await build_memory_context(db, user.id, message)
        if memory_ctx:
            system_parts.append("MEMORY:\n" + memory_ctx)
    except Exception:
        pass  # best-effort — never block chat

    system_parts.append(
        "Be concise, direct, and helpful. Use markdown sparingly."
    )

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(system_parts)}]

    # Session-scoped history if session_id provided, otherwise global recent history
    if session_id:
        stmt = (
            select(Message)
            .where(Message.session_id == session_id, Message.user_id == user.id)
            .order_by(Message.created_at.desc())
            .limit(history_limit)
        )
    else:
        stmt = (
            select(Message)
            .where(Message.user_id == user.id)
            .order_by(Message.created_at.desc())
            .limit(history_limit)
        )
    history = list(reversed((await db.execute(stmt)).scalars().all()))
    for m in history:
        role = m.role if m.role in ("user", "assistant") else "user"
        messages.append({"role": role, "content": m.content})

    messages.append({"role": "user", "content": message})
    return messages
