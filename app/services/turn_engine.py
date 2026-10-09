"""Turn engine — one adaptive LLM call per student turn.

Theory: a tutor never writes the whole lesson before hearing the student.
Each turn the engine reads the lesson pointer from Postgres, detects the
student signal with regex first (no LLM needed for control words), then makes
exactly one strict-JSON call that returns a move plus the words to say.

Moves: hook | chunk | probe_question | alt | quiz | done
Signals: new_topic | advance | probe | question
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson_models import Lesson
from app.services import lesson_store

logger = logging.getLogger(__name__)

_ADVANCE_EXACT = {
    "next", "continue", "got it", "gotcha", "okay", "ok", "k", "yeah",
    "yep", "yes", "sure", "go", "more", "advance", "i get it",
    "i understood", "makes sense", "next one", "next chunk", "next please",
}

_PROBE_PHRASES = (
    "i don't get it", "i dont get it", "didn't get", "didnt get",
    "explain again", "different analogy", "different example",
    "i'm lost", "im lost", "i'm confused", "im confused", "not clear",
    "still confused", "still lost",
)


def _has_phrase(haystack: str, needle: str) -> bool:
    return bool(re.search(rf"\b{re.escape(needle)}\b", haystack))


_ADVANCE_PHRASES = (
    "got it", "get it", "makes sense", "next", "continue", "understood",
    "i see", "keep going", "go on", "move on",
)

_GREETINGS = {
    "hi", "hello", "hey", "salam", "aoa", "assalamualaikum",
    "assalamu alaikum", "good morning", "good afternoon", "good evening",
    "yo", "sup", "howdy", "hi pixie", "hello pixie", "hey pixie",
}

_TOOL_RE = re.compile(
    r"(note|save .*note|write .*note|vault|upload|pdf|file|deadline|exam|"
    r"assignment|remind|schedule|calendar|quiz me|test me|flashcard)",
    re.IGNORECASE,
)

# Hard ceiling per turn call: past this the engine serves the safe fallback
# instead of hanging. Worst case per turn is ~15s classify + 15s router + 45s
# writer, only when the provider stalls every call.


def _pick_lesson(
    lessons: list[Lesson], session_id: uuid.UUID | None
) -> Lesson | None:
    """Active lesson wins. Prefer the lesson bound to this chat session so a
    stray hook from an old misfire can never hijack the student's turns."""
    if not lessons:
        return None
    if session_id is not None:
        for les in lessons:
            if les.session_id == session_id and les.phase != "complete":
                return les
        return None
    for les in lessons:
        if les.phase != "complete":
            return les
    return lessons[0]


def detect_signal(raw: str) -> str:
    """advance | probe | question. Anything else is new_topic (decided by caller)."""
    msg = raw.lower().strip()
    if msg in _ADVANCE_EXACT:
        return "advance"
    if msg in {"no", "stop", "wait", "idk", "i dunno", "dunno"}:
        return "probe"
    if any(_has_phrase(msg, p) for p in _PROBE_PHRASES):
        return "probe"
    # Probe wins over advance: "i don't get it" contains "get it" but is stuck.
    if any(_has_phrase(msg, p) for p in _ADVANCE_PHRASES):
        return "advance"
    if msg.endswith("?") or msg.startswith(("what", "why", "how", "when", "where", "who", "can", "is ", "are ", "do ", "does ")):
        return "question"
    if len(msg.split()) <= 2:
        # Bare fragment ("two", "mitosis"). Control words already matched
        # above, so this is content: an answer attempt if a lesson is live,
        # otherwise too thin to start one.
        return "short"
    return "question"


TURN_SYSTEM = """You are Pixie, a patient tutor for a school inclusion department. One idea per turn. Simple words. No jargon stacking. Never repeat a failed explanation verbatim.

Reply ONLY with strict JSON, no fences:
{
  "title": "<short title, max 8 words>",
  "body": "<one paragraph, one idea, max 80 words. Hook: one definition plus one relatable analogy. Alt: same idea, completely different analogy, simpler words.>",
  "clothing": "analogy_fun" | "analogy_rational" | "analogy_imag" | "plain",
  "check_question": "<one short question, max 15 words>",
  "about": "<on hook moves only: pin the topic meaning in max 20 words so later turns never drift, e.g. 'iron oxidation of metal, not the programming language'>"
}

Check-question law (retrieval-first): every check must force recall, never
recognition. Ban yes-no and does-it questions entirely. Ask what, why, or how.
"What does the new cell get from the old one?" passes. "Does mitosis create
identical cells?" fails and must never ship. Prefer why when the concept has a
mechanism: "Why must the cell copy its instructions first?"

Rules:
- Keep scientific claims precise. Define the relevant substance or process in simple words rather than replacing it with an inaccurate generic term.
- Explain the usual mechanism without inventing universal rules. Qualify statements when exceptions exist; check questions must not have false premises.
- An analogy illustrates a mechanism; it must not assert that the imagined example is a literal scientific fact. If it obscures the mechanism, use a plain explanation instead.
- A verified_numeric_judgment is exact arithmetic verification: do not contradict it. Unassessable means clarify the input, never call it wrong.
- The routing decision (move, verdict) is already made and given in the request. Your job is ONLY the words.
- If rewrite_guide is present, follow it exactly. Never resend the old body.
- If verdict_prefix is present, the reply already opened with it. Do NOT repeat it. Continue straight into the teaching.
- Stay on topic_sense when it is present. Never switch meanings mid-lesson (rust the metal oxidation vs Rust the language, banks vs river banks). If the student asks about the other meaning, that is a new_topic move.
- Never utter system words: Hook, Chunk, Alt, probe, verdict, failure mode, pending check, prior items. Never restate earlier items or list what was taught. Teach forward only.
- probe_question moves stay tiny: one short question plus one line of setup, max 40 words total.
- No emojis. No "great question". No obviously, as you know, naturally."""


ROUTER_SYSTEM = """You route one student turn for a tutor. Reply ONLY with strict JSON, no fences:
{
  "move": "hook" | "chunk" | "probe_question" | "alt" | "quiz" | "done" | "new_topic",
  "verdict": "correct" | "partial" | "wrong" | "none",
  "failure_mode": "words" | "analogy" | "logic" | "idea" | "none",
  "topic": "<new topic name, only on new_topic>",
  "total_chunks": <3 to 6, only on hook or new_topic>
}

Rules:
- Hook only when prior_items is empty. Otherwise chunk, alt, or probe_question.
- Probe signal: failure_mode is already diagnosed in the request. Move alt, or probe_question to dig first.
- Followup: judge any answer attempt against pending_check. Then move chunk (advance), alt (re-teach), probe_question (dig deeper).
- Verdict generously: a short or rough answer that carries the core idea is correct. A partly right answer is partial, never wrong. Reserve wrong for answers that contradict the idea. When in doubt between none and a verdict, give the verdict. A bare number or noun that matches the expected answer is correct.
- Examples. pending_check "How many identical cells result from one division?", student says "two" → verdict correct, move chunk. Student says "three" → verdict wrong, move alt. Student says "make a similar copy" to "What does the photocopier do to the page?" → verdict correct, move chunk. Student says "why?" with no answer inside → verdict none, move probe_question.
- New_topic ONLY when the question is clearly about something else entirely.
- Advance: chunk. No lesson and no prior items: hook."""


ROUTER_TIMEOUT_S = 15.0
WRITER_TIMEOUT_S = 45.0



async def route_turn(
    db: AsyncSession,
    user_id: uuid.UUID,
    raw_message: str,
    session_id: uuid.UUID | None,
    grade_level: str | None,
    call_llm_json,
) -> dict:
    """Resolve + route one turn. Returns {"payload": ...} for instant answers
    (greeting, redirect, escalate) or {"route": {...}} for the writer to finish.
    The router call is tiny by design so verdicts leave in seconds."""
    t0 = time.monotonic()
    msg_lower = raw_message.lower().strip()

    # Greetings are never lessons. No DB writes, no LLM call, instant.
    if msg_lower in _GREETINGS:
        lessons = await lesson_store.list_lessons(db, user_id)
        active = _pick_lesson(lessons, session_id)
        if active and active.phase != "complete":
            delta = (
                f"Hey. We were in the middle of **{active.topic}**. "
                "Say next when you're ready to continue, or ask me anything."
            )
        else:
            delta = (
                "Hey, I'm Pixie. Ask me anything you're studying and "
                "we'll take it step by step."
            )
        return {
            "payload": {
            "delta": delta,
            "structured": True,
            "event": "greeting",
            "signal": "greeting",
            "phase": active.phase if active else "none",
            "topic": active.topic if active else "",
            "latency_ms": int((time.monotonic() - t0) * 1000),
            },
            "route": None,
        }

    # Procedural requests belong to the app tabs, not the tutor. Redirect
    # honestly instead of lessonizing them. No lesson, no LLM call.
    if _TOOL_RE.search(raw_message) and len(msg_lower.split()) <= 12:
        return {
            "payload": {
            "delta": (
                "That's for another tab: notes live in your Notebook, files in "
                "Files, deadlines in Calendar. Here in chat, I teach. "
                "Ask me anything you're studying."
            ),
            "structured": True,
            "event": "redirect",
            "signal": "procedural",
            "phase": "none",
            "topic": "",
            "latency_ms": int((time.monotonic() - t0) * 1000),
            },
            "route": None,
        }

    signal = detect_signal(raw_message)

    if signal in ("advance", "probe"):
        lessons = await lesson_store.list_lessons(db, user_id)
        lesson = _pick_lesson(lessons, session_id)
        if lesson is None or lesson.phase == "complete":
            return {"route": None, "payload": {
                "delta": "What would you like to learn? Choose an existing session to resume it, or tell me a topic.",
                "structured": True, "event": "prompt", "signal": signal,
                "phase": "none", "topic": "", "latency_ms": int((time.monotonic()-t0)*1000),
            }}
    elif signal == "question":
        # Inside an active lesson there are no new topics by default, only
        # three things: confusion (probe), an answer attempt, or a genuine
        # follow-up. Confusion goes to probe. Everything else stays on the
        # thread as followup and the model judges any embedded answer. A
        # brand-new topic only starts when there is no active lesson at all.
        from app.services.failure_modes import regex_mode as _rx

        lessons = await lesson_store.list_lessons(db, user_id)
        lesson = _pick_lesson(lessons, session_id)
        if lesson is not None and _rx(raw_message) is not None:
            signal = "probe"
        elif lesson is not None:
            signal = "followup"
    elif signal == "short":
        # Bare fragment. With a live lesson it is an answer attempt.
        # Without one it is too thin to teach: ask what to learn, no lesson.
        lessons = await lesson_store.list_lessons(db, user_id)
        lesson = _pick_lesson(lessons, session_id)
        if lesson is not None:
            signal = "followup"
        else:
            return {
                "payload": {
                    "delta": "Tell me what you want to learn, for example "
                             "\"what is mitosis?\" and we will take it step by step.",
                    "structured": True,
                    "event": "prompt",
                    "signal": "short",
                    "phase": "none",
                    "topic": "",
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                },
                "route": None,
            }
    else:
        lesson = None

    if signal == "new_topic" or (signal == "question" and lesson is None):
        topic = raw_message.strip()
        existing = await lesson_store.get_lesson(db, user_id, topic)
        if existing and session_id is not None and existing.session_id != session_id:
            return {"route": None, "payload": {
                "delta": "This topic already has a learning record in another session. Open that session to resume it; I won't silently transfer its progress here.",
                "structured": True, "event": "resume_required", "signal": "question",
                "phase": "none", "topic": topic, "latency_ms": int((time.monotonic()-t0)*1000),
            }}
        if existing and existing.phase != "complete":
            lesson = existing
            signal = "question"
        else:
            lesson, _ = await lesson_store.get_or_create_lesson(
                db, user_id, topic, session_id=session_id, grade_level=grade_level
            )

    assert lesson is not None
    items = await lesson_store.get_items(db, lesson.id)
    prior = [
        {"kind": it.kind, "title": it.title, "body": it.body[:300]}
        for it in items[-4:]
    ]

    # Probe path: diagnose first, cap retries, escalate to teacher at the cap.
    failure_mode: str | None = None
    if signal == "probe":
        from app.services import failure_modes as _fm

        alt_count = sum(
            1 for it in items
            if it.kind == "alt" and it.idx == lesson.chunk_index
        )
        if alt_count >= _fm.MAX_RE_CHUNKS:
            return await _support_limit(db, lesson, user_id, signal, t0)
        last_body = ""
        for it in reversed(items):
            if it.kind in ("hook", "chunk", "alt"):
                last_body = it.body
                break
        failure_mode = await _fm.classify_failure_mode(
            last_body, raw_message, call_llm_json
        )

    user_payload: dict = {
        "topic": lesson.topic,
        "topic_sense": lesson.about,
        "grade": grade_level or lesson.grade_level or "unknown",
        "phase": lesson.phase,
        "chunk_index": lesson.chunk_index,
        "student_signal": signal,
        "student_message": raw_message.strip()[:1000],
        "prior_items": prior,
    }
    if failure_mode:
        from app.services.failure_modes import MODE_GUIDE

        user_payload["failure_mode"] = failure_mode
        user_payload["rewrite_guide"] = MODE_GUIDE[failure_mode]
    if signal == "followup":
        # The model needs the pending check to judge the answer attempt.
        for it in reversed(items):
            if it.kind in ("hook", "chunk", "alt", "probe_question") and it.check_question:
                user_payload["pending_check"] = {
                    "question": it.check_question,
                    "idea": (it.body or "")[:300],
                }
                break
    from app.services.mastery import profile_line as _profile_line

    try:
        pline = await _profile_line(db, user_id)
        if pline:
            user_payload["learner_profile"] = pline
    except Exception:
        pass
    user_msg = json.dumps(user_payload)

    # Two-call split. Router is tiny and fast (verdict out in seconds).
    # Writer does the words. Either can fail into a safe default.
    import asyncio as _turn_aio

    def _default_move() -> str:
        if signal == "advance":
            return "chunk"
        if signal == "probe":
            return "alt"
        if signal == "followup":
            return "probe_question"
        return "hook"

    from app.services.numeric_verification import verify_arithmetic_question
    numeric_judgment = None
    if signal == "followup" and user_payload.get("pending_check"):
        numeric_judgment = verify_arithmetic_question(user_payload["pending_check"]["question"], raw_message)
    if numeric_judgment is not None:
        routed = {"move": "chunk" if numeric_judgment == "correct" else "alt" if numeric_judgment == "incorrect" else "probe_question",
            "verdict": "correct" if numeric_judgment == "correct" else "wrong" if numeric_judgment == "incorrect" else "none",
            "failure_mode": "none"}
        user_payload["verified_numeric_judgment"] = numeric_judgment
    else:
        try:
            routed = await _turn_aio.wait_for(
                call_llm_json(ROUTER_SYSTEM, user_msg, max_tokens=150),
                timeout=ROUTER_TIMEOUT_S,
            )
            if not isinstance(routed, dict):
                raise ValueError("router non-JSON")
        except Exception as e:
            logger.warning("router failed, defaulting by signal: %s", e)
            routed = {"move": _default_move(), "verdict": "none",
                      "failure_mode": "none"}

    move = str(routed.get("move", "") or "").lower().strip()
    if move not in ("hook", "chunk", "probe_question", "alt", "quiz", "done",
                    "new_topic"):
        move = _default_move()

    if move == "hook" and items:
        move = "chunk"

    verdict = str(routed.get("verdict", "none") or "none").lower().strip()
    if verdict not in ("correct", "partial", "wrong", "none"):
        verdict = "none"

    if signal == "followup" and verdict in ("wrong", "partial") and move in ("alt", "probe_question"):
        from app.services.failure_modes import MAX_RE_CHUNKS
        alternatives = sum(it.kind == "alt" and it.idx == lesson.chunk_index for it in items)
        if alternatives >= MAX_RE_CHUNKS:
            return await _support_limit(db, lesson, user_id, signal, t0)

    if not items:
        verdict = "none"
        if move != "new_topic": move = "hook"

    rmode = str(routed.get("failure_mode", "none") or "none").lower().strip()
    if failure_mode is None and rmode in ("words", "analogy", "logic", "idea"):
        failure_mode = rmode

    # Verdict goes out instantly on followup; the writer must not repeat it.
    early_delta: str | None = None
    verdict_prefix = ""
    if signal == "followup":
        verdict_prefix = {"correct": "That's right. ",
                          "partial": "Partly right. ",
                          "wrong": "Not quite. "}.get(verdict, "")
        if verdict_prefix:
            early_delta = verdict_prefix.strip()

    writer_payload = dict(user_payload)
    writer_payload["decision"] = {
        "move": move, "verdict": verdict,
        "failure_mode": failure_mode,
        "verdict_prefix": verdict_prefix or None,
    }
    try:
        total_chunks = max(3, min(6, int(routed.get("total_chunks", 4))))
    except (TypeError, ValueError):
        total_chunks = 4
    new_topic_name = (
        str(routed.get("topic", "") or "").strip()[:500] or None
    )
    if move == "new_topic" and new_topic_name:
        writer_payload.update(topic=new_topic_name, topic_sense="", prior_items=[], phase="hook", chunk_index=0)
        writer_payload.pop("pending_check", None)
        writer_payload["decision"].update(verdict="none", verdict_prefix=None)
        verdict, early_delta = "none", None

    return {
        "payload": None,
        "route": {
            "lesson": lesson,
            "items": items,
            "signal": signal,
            "move": move,
            "verdict": verdict,
            "failure_mode": failure_mode,
            "early_delta": early_delta,
            "total_chunks": total_chunks,
            "new_topic": new_topic_name or lesson.topic,
            "writer_payload": writer_payload,
            "t0": t0,
            "grade_level": grade_level,
            "session_id": session_id,
            "raw_message": raw_message,
        },
    }


async def _support_limit(db, lesson, user_id, signal, t0):
    # A request for human support is not a validated wrong answer.
    await lesson_store.record_event(db, lesson, user_id, student_signal=signal,
        model_move="escalate", latency_ms=int((time.monotonic()-t0)*1000), understood=None)
    from app.services.mastery import count_escalation
    await count_escalation(db, user_id)
    await db.commit()
    return {"route": None, "payload": {
        "delta": "Let's pause this part. You can return later, choose another topic, or ask a teacher or support person for help.",
        "structured": True, "event": "escalate", "topic": lesson.topic,
        "signal": signal, "phase": lesson.phase, "chunk_index": lesson.chunk_index,
        "total_chunks": lesson.total_chunks, "latency_ms": int((time.monotonic()-t0)*1000),
    }}


def _valid_teaching_output(out: dict) -> bool:
    body, question = out.get("body"), out.get("check_question")
    if not isinstance(body, str) or not body.strip() or len(body.split()) > 80:
        return False
    if not isinstance(question, str) or not question.strip() or len(question.split()) > 15:
        return False
    if re.match(r"^(does|do|did|is|are|can|have|has)\b", question.strip(), re.I):
        return False
    return out.get("clothing", "plain") in ("plain", "analogy_fun", "analogy_rational", "analogy_imag")


def _unavailable_payload(lesson: Lesson, t0: float) -> dict:
    return {
        "delta": "I couldn't prepare the next teaching step. This is a system problem. Your learning progress has not changed. Please try again.",
        "structured": True, "event": "unavailable", "retryable": True,
        "topic": lesson.topic, "phase": lesson.phase,
        "chunk_index": lesson.chunk_index, "total_chunks": lesson.total_chunks,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "verdict": "none",
    }


async def write_turn(
    db: AsyncSession,
    user_id: uuid.UUID,
    route: dict,
    call_llm_json,
) -> dict:
    """Writer call plus storage plus mastery plus events. Returns SSE payload."""
    import asyncio as _turn_aio

    lesson = route["lesson"]
    items = route["items"]
    signal = route["signal"]
    move = route["move"]
    verdict = route["verdict"]
    failure_mode = route["failure_mode"]
    writer_payload = route["writer_payload"]
    t0 = route["t0"]
    grade_level = route["grade_level"]
    session_id = route["session_id"]

    try:
        out = await _turn_aio.wait_for(
            call_llm_json(TURN_SYSTEM, json.dumps(writer_payload)),
            timeout=WRITER_TIMEOUT_S,
        )
        if not isinstance(out, dict):
            raise ValueError("writer non-JSON")
    except Exception as e:
        logger.warning("teaching writer unavailable: %s", type(e).__name__)
        return _unavailable_payload(lesson, t0)

    # Provider failures and invalid presentation are not student evidence.
    # Reject before any pointer, item, mastery or event writes.
    if not _valid_teaching_output(out):
        logger.warning("teaching writer returned invalid presentation")
        return _unavailable_payload(lesson, t0)

    body = str(out.get("body", "") or "")[:1200]
    title = str(out.get("title", "") or "")[:200]
    clothing = out.get("clothing", "analogy_fun")
    check_q = str(out.get("check_question", "") or "")[:300]
    understood = out.get("understood")

    # The verdict already went out as its own instant event. If the writer
    # repeated the prefix anyway, strip it so the student never reads it twice.
    for _p in ("That's right. ", "Partly right. ", "Not quite. "):
        if body.startswith(_p):
            body = body[len(_p):].lstrip()
            break

    if move == "new_topic":
        # The model decided the thread changed. New lesson row, hook stored.
        lesson, _ = await lesson_store.get_or_create_lesson(
            db, user_id, route["new_topic"], session_id=session_id,
            grade_level=grade_level,
        )
        lesson.total_chunks = route["total_chunks"]
        lesson.phase = "hook"
        lesson.chunk_index = 0
        about = str(out.get("about", "") or "").strip()[:200]
        if about:
            lesson.about = about
        await lesson_store.add_item(
            db, lesson, kind="hook", body=body, idx=0,
            title=title, clothing=clothing, check_question=check_q,
        )

    if move == "hook":
        lesson.total_chunks = route["total_chunks"]
        lesson.phase = "hook"
        about = str(out.get("about", "") or "").strip()[:200]
        if about:
            lesson.about = about
        await lesson_store.add_item(
            db, lesson, kind="hook", body=body, idx=0,
            title=title, clothing=clothing, check_question=check_q,
        )
    elif move == "alt":
        await lesson_store.set_phase(db, lesson, "probe")
        await lesson_store.add_item(
            db, lesson, kind="alt", body=body,
            title=title, clothing=clothing, check_question=check_q,
            failure_mode=failure_mode or "analogy",
        )
    elif move == "done":
        await lesson_store.set_phase(db, lesson, "complete")
    elif move in ("chunk", "quiz"):
        if (signal == "advance" or (signal == "followup" and verdict == "correct")) and items:
            from app.services import mastery as _madv

            old_idx = lesson.chunk_index
            had_alt = next(
                (it for it in items if it.kind == "alt" and it.idx == old_idx), None
            )
            if had_alt:
                # Quiz-gated: advances never raise scores. Credit the clothing
                # that helped, nothing more.
                await _madv.count_advance(
                    db, user_id, helped_clothing=had_alt.clothing or "analogy_fun"
                )
            else:
                await _madv.count_advance(db, user_id)
            await lesson_store.advance(db, lesson)
        await lesson_store.add_item(
            db, lesson, kind=move, body=body,
            title=title, clothing=clothing, check_question=check_q,
        )
        if lesson.phase == "hook":
            await lesson_store.set_phase(db, lesson, "build")
    else:  # probe_question: preserve the presented check even when pointer stays
        await lesson_store.set_phase(db, lesson, "probe")
        await lesson_store.add_item(db, lesson, kind="probe_question", body=body,
            title=title, clothing=clothing, check_question=check_q)

    latency_ms = int((time.monotonic() - t0) * 1000)
    if signal == "probe":
        # Struggle is evidence: concept drops, failure mode gets a vote.
        from app.services import mastery as _mprb

        _pkey = _mprb.concept_key(lesson.topic_norm, lesson.chunk_index)
        _cur = next(
            (it for it in items
             if it.kind in ("hook", "chunk") and it.idx == lesson.chunk_index), None
        )
        _plabel = (_cur.title or lesson.topic) if _cur else lesson.topic
        await _mprb.observe(db, user_id, _pkey, _plabel, _mprb.DOWN_PROBE)
        await _mprb.count_probe(db, user_id, failure_mode or "idea")
    if signal == "followup" and verdict in ("correct", "wrong"):
        # A judged answer is evidence too. Quiz-gated: correct answers count
        # the advance but never raise scores. Wrong answers lower.
        from app.services import mastery as _mver

        _vkey = _mver.concept_key(lesson.topic_norm, lesson.chunk_index)
        _vcur = next(
            (it for it in items
             if it.kind in ("hook", "chunk") and it.idx == lesson.chunk_index), None
        )
        _vlabel = (_vcur.title or lesson.topic) if _vcur else lesson.topic
        if verdict == "wrong":
            await _mver.observe(db, user_id, _vkey, _vlabel, _mver.DOWN_PROBE)
            await _mver.count_probe(db, user_id, "idea")
    if verdict == "correct": understood = True
    elif verdict == "wrong": understood = False
    await lesson_store.record_event(
        db, lesson, user_id,
        student_signal=signal, model_move=move,
        latency_ms=latency_ms,
        understood=bool(understood) if understood is not None else None,
    )
    if lesson.phase == "complete":
        from app.services.xp import award_completed_lesson_xp

        await award_completed_lesson_xp(db, user_id, lesson.id)
    await db.commit()

    # The verdict already went out as its own instant event and the writer
    # was told not to repeat it, so the final delta carries no prefix.
    if verdict == "correct":
        understood = True
    elif verdict == "wrong":
        understood = False
    delta = f"**{title}**\n\n{body}\n\n_{check_q}_" if title else f"{body}\n\n_{check_q}_"
    return {
        "delta": delta,
        "structured": True,
        "event": move,
        "topic": lesson.topic,
        "signal": signal,
        "phase": lesson.phase,
        "chunk_index": lesson.chunk_index,
        "total_chunks": lesson.total_chunks,
        "title": title,
        "body": body,
        "clothing": clothing,
        "check_question": check_q,
        "latency_ms": latency_ms,
        "verdict": verdict,
    }
