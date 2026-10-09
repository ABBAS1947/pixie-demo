"""Chat endpoint — the heart of the pixie.

POST /chat/message (SSE stream):
1. validate JWT -> user_id (identity from token only)
2. load persona + peer id
3. pull Honcho peer context
4. embed message, retrieve user's notes (user_id scoped)
5. compose prompt, stream DeepSeek reply
6. persist messages, signal Honcho, fire post-turn background task
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.users import _auth_id_from_token
from app.core.db import get_db
from app.core.rate_limit import chat_limiter
from app.services.cost_firewall import MESSAGES as _LIMIT_MSGS, check_turn_budget
from app.models.models import Message, Note, Session
from app.services.calendar_tools import (
    CALENDAR_TOOLS, NOTES_TOOLS, FILES_TOOLS,
    execute_calendar_tool, execute_notes_tool, execute_files_tool,
)
from app.services.llm_registry import get_provider
from app.services.honcho_client import HonchoClient
from app.services.ollama_client import embed_text
from app.services.prompt_builder import build_messages_session
from app.services.retrieval import search_notes
from app.services.chat_titles import title_from_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Valid tool names so we only parse known tools from text fallback.
_KNOWN_TOOLS = {"create_deadline", "list_deadlines", "update_deadline",
                "delete_deadline", "create_note", "list_notes",
                "search_notes", "read_note", "list_files", "read_file"}

# Tool intent gate. The chat model (qwen3.8-flash) over-triggers tool calls on
# ordinary questions — "what is my name?" caused it to call a tool, return no
# text, and spin the tool-loop (measured: 11s first-token, 0 text, 1 tool call).
# Only attach the tool schema when the student's message clearly needs a
# note/file/calendar action, so plain Q&A answers directly and fast.
import re as _re

_TOOL_INTENT = _re.compile(
    r"(due|deadline|exam|test|assignment|submit|remind(er)?|schedule|calendar|"
    r"note|vault|save|record|file|upload|pdf|read_file|list_files|search_notes|"
    r"tomorrow|today|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    _re.IGNORECASE,
)


def _needs_tools(text: str) -> bool:
    """Whether to attach the tool schema for this message (intent gate)."""
    if not text:
        return False
    # A word like 'read' alone shouldn't force tools; require a concrete signal.
    return bool(_TOOL_INTENT.search(text))


def _try_parse_tool_calls(text: str) -> list[dict] | None:
    """Fallback: extract tool calls embedded as JSON in the model's text.

    Some reasoning models output tool calls as JSON blocks in their text
    instead of using the standard tool_calls field.  We look for JSON
    objects that contain a "name" matching a known tool.
    """
    import re
    # Find all JSON-like blocks (```json ... ``` or bare { ... })
    for m in re.finditer(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        name = obj.get("name", "")
        if name in _KNOWN_TOOLS:
            return [{"id": "", "name": name,
                      "arguments": json.dumps(obj.get("arguments", {}))}]
    # Also try bare JSON objects in the text
    for m in re.finditer(r'(?<!\w)(\{[^{}]*"name"\s*:\s*"[^"]+"[^{}]*\})', text):
        try:
            obj = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        name = obj.get("name", "")
        if name in _KNOWN_TOOLS:
            return [{"id": "", "name": name,
                      "arguments": json.dumps(obj.get("arguments", {}))}]
    return None


async def _get_user_or_404(auth_id: str, db: AsyncSession):
    """Resolve auth_id to User or raise 404."""
    from app.models.models import User
    from app.services.account_lifecycle import assert_auth_active, assert_user_active
    await assert_auth_active(db, auth_id)
    user = (
        await db.execute(select(User).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not provisioned")
    await assert_user_active(db, user.id)
    from app.services.processing_boundary import bind_actor
    bind_actor(user.id)
    return user

bearer = HTTPBearer(auto_error=False)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: uuid.UUID | None = None


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


async def _post_turn_tasks(db: AsyncSession, user_id: uuid.UUID, text: str) -> None:
    """Background work after the reply is sent. No latency to the user.

    Currently: deadline extraction probe. Cheap keyword pre-filter, then
    structured extraction. Add note-taking trigger here later.
    """
    # Cheap pre-filter: only escalate when a date-ish signal is present.
    import re

    if not re.search(r"\b(due|deadline|exam|test|assignment|submit|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", text, re.IGNORECASE):
        return

    from datetime import datetime, timezone

    from app.models.models import Deadline

    provider = get_provider("extraction")
    try:
        result = await provider.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract deadlines from the student message. Reply ONLY with JSON: "
                        '{"deadlines":[{"title":string,"due_at":"YYYY-MM-DDTHH:MM:SSZ",'
                        '"kind":"assignment|exam|project"}]} '
                        'Return {"deadlines":[]} if none.'
                    ),
                },
                {"role": "user", "content": text},
            ],
            json_mode=True,
            temperature=0,
        )
        parsed = json.loads(result["content"])
    except Exception:
        return  # loggable failure, never a silent crash of the turn

    now = datetime.now(timezone.utc)
    for d in parsed.get("deadlines", []):
        try:
            due = datetime.fromisoformat(d["due_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if due <= now:
            continue
        if d["kind"] not in ("assignment", "exam", "project"):
            continue
        existing = await db.execute(
            select(Deadline).where(Deadline.user_id == user_id, Deadline.title == d["title"])
        )
        if existing.scalar_one_or_none() is not None:
            continue
        db.add(
            Deadline(
                user_id=user_id,
                title=d["title"][:500],
                due_at=due,
                kind=d["kind"],
                source="conversation",
                confirmed=False,  # must be confirmed before it counts
            )
        )
    await db.commit()


@router.post("/chat/message")
async def chat_message(
    body: ChatRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    auth_id = _auth_id_from_token(credentials)
    chat_limiter.check(auth_id)

    from sqlalchemy.orm import selectinload

    from app.models.models import User

    user = (
        await db.execute(select(User).options(selectinload(User.persona)).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not provisioned")

    # Cost firewall: normal chat burns the same provider tokens as Learn.
    _budget = await check_turn_budget(db, user)
    if _budget != "ok":
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _LIMIT_MSGS[_budget])

    # session: reuse given, else create one
    if body.session_id is not None:
        sess = (
            await db.execute(select(Session).where(Session.id == body.session_id, Session.user_id == user.id))
        ).scalar_one_or_none()
        if sess is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    else:
        sess = Session(user_id=user.id, subject=title_from_message(body.message))
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
        # Mirror the session in Honcho so message writes have a home.
        # Best-effort: Honcho being down must never break chat.
        try:
            await HonchoClient().create_session(user.honcho_peer_id, str(sess.id))
        except Exception:
            pass

    # persist the user message immediately so nothing is lost
    db.add(Message(session_id=sess.id, user_id=user.id, role="user", content=body.message))
    await db.commit()

    sess_id = str(sess.id)

    async def event_stream():
        yield f"data: {json.dumps({'session_id': sess_id})}\n\n"
        # 1. Honcho context
        honcho = HonchoClient()
        try:
            honcho_ctx = await honcho.get_peer_context(user.honcho_peer_id)
        except Exception:
            honcho_ctx = None
            logger.debug("Honcho context unavailable for user %s", user.id)

        # 2. embed + retrieve (user_id scoped)
        try:
            vec = await embed_text(body.message)
            notes = await search_notes(db, user.id, vec, limit=5)
        except Exception:
            notes = []
            logger.debug("Embedding/retrieval failed for user %s", user.id)

        # 3. compose + stream
        try:
            messages = await build_messages_session(db, user, body.message, notes, honcho_ctx, session_id=sess.id)
        except Exception:
            logger.debug("Session-scoped prompt failed for user %s, using fallback", user.id)
            messages = [
                {
                    "role": "system",
                    "content": "You are Pixie, a patient study partner. Answer the student's question.",
                },
                {"role": "user", "content": body.message},
            ]

        provider = get_provider("chat")
        full = ""
        tool_calls = None
        iterations = 0
        # Tool intent gate: only offer tools when the message signals a
        # note/file/calendar action, so plain Q&A never enters the tool loop.
        ALL_TOOLS = (CALENDAR_TOOLS + NOTES_TOOLS + FILES_TOOLS) if _needs_tools(body.message) else None
        try:
            # Tool loop: the model may call calendar and notes tools
            # before answering. Each pass either streams text (done)
            # or returns tool_calls to execute. Max 3 round-trips.
            while True:
                iterations += 1
                async for item in provider.stream(messages, tools=ALL_TOOLS):
                    if isinstance(item, dict):
                        if "text" in item:
                            full += item["text"]
                            yield f"data: {json.dumps({'delta': item['text']})}\n\n"
                        elif "tool_calls" in item:
                            tool_calls = item["tool_calls"]
                    else:
                        full += item
                        yield f"data: {json.dumps({'delta': item})}\n\n"

                # Fallback: some reasoning models embed tool calls as JSON
                # in their text response instead of using the standard
                # tool_calls field.  Try to parse them.
                if not tool_calls and full:
                    tool_calls = _try_parse_tool_calls(full)

                if not tool_calls or iterations > 3:
                    break

                # Execute the requested tools, then feed results back.
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                messages.append(assistant_msg)
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    name = tc.get("name", "")
                    # Route to the right executor based on tool name
                    if name in ("create_note", "list_notes", "search_notes", "read_note"):
                        result = await execute_notes_tool(db, user, name, args)
                    elif name in ("list_files", "read_file"):
                        result = await execute_files_tool(db, user, name, args)
                    else:
                        result = await execute_calendar_tool(db, user, name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps(result),
                        }
                    )
                tool_calls = None
        except Exception as e:
            logger.error("Chat stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': 'An error occurred. Please try again.'})}\n\n"
            full = ""  # don't persist a half reply as if complete
        else:
            # persist assistant reply
            db.add(Message(session_id=sess.id, user_id=user.id, role="assistant", content=full))
            await db.commit()
            # signal Honcho (it learns from this exchange)
            try:
                await honcho.add_message(str(sess.id), body.message, user.honcho_peer_id)
            except Exception:
                pass
        finally:
            yield "data: [DONE]\n\n"

    # MEDIUM-05: Post-turn work happens AFTER [DONE] is sent to the client.
    # These run outside the SSE generator to avoid blocking the response.
    try:
        await _post_turn_tasks(db, user.id, body.message + "\n" + full)
    except Exception:
        pass
    try:
        from app.services.post_turn import run_post_turn_analysis
        await run_post_turn_analysis(
            db, sess.id, user.id,
            grade_level=user.grade_level or "",
        )
    except Exception:
        pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Session management ─────────────────────────────────────────────────────


@router.get("/chat/sessions")
async def list_sessions(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's chat sessions, most recent first.
    Uses a single query with window function to avoid N+1."""
    from sqlalchemy import func, over
    from app.models.models import User

    auth_id = _auth_id_from_token(credentials)
    user = await _get_user_or_404(auth_id, db)

    # Single query: get sessions with message count + last message via window function
    last_msg_sq = (
        select(
            Message.session_id,
            Message.id.label("last_id"),
            Message.content.label("last_content"),
            Message.role.label("last_role"),
            func.row_number().over(
                partition_by=Message.session_id,
                order_by=Message.created_at.desc()
            ).label("rn"),
        )
        .where(Message.user_id == user.id)
    ).subquery()

    first_user_sq = (
        select(
            Message.session_id,
            Message.id.label("first_id"),
            Message.content.label("first_user_content"),
            func.row_number().over(
                partition_by=Message.session_id,
                order_by=(Message.created_at.asc(), Message.id.asc()),
            ).label("rn"),
        )
        .where(Message.user_id == user.id, Message.role == "user")
    ).subquery()

    stmt = (
        select(
            Session.id,
            Session.subject,
            Session.started_at,
            func.count(Message.id).label("message_count"),
            last_msg_sq.c.last_content,
            last_msg_sq.c.last_id,
            last_msg_sq.c.last_role,
            first_user_sq.c.first_user_content,
            first_user_sq.c.first_id,
        )
        .outerjoin(Message, Message.session_id == Session.id)
        .outerjoin(last_msg_sq, (last_msg_sq.c.session_id == Session.id) & (last_msg_sq.c.rn == 1))
        .outerjoin(first_user_sq, (first_user_sq.c.session_id == Session.id) & (first_user_sq.c.rn == 1))
        .where(Session.user_id == user.id)
        .group_by(Session.id, Session.subject, Session.started_at, last_msg_sq.c.last_content, last_msg_sq.c.last_id, last_msg_sq.c.last_role, first_user_sq.c.first_user_content, first_user_sq.c.first_id)
        .order_by(Session.started_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    sessions = []
    for row in rows:
        from app.core.config import settings
        from app.services.encrypted_orm import decrypt_value
        def readable(value, table, field, resource):
            if settings.content_encryption_mode != "required" or value is None:
                return value
            return decrypt_value(value, table=table, field=field, owner=str(user.id), resource=str(resource))
        last_content = readable(row.last_content, "messages", "content", row.last_id)
        first_content = readable(row.first_user_content, "messages", "content", row.first_id)
        subject = readable(row.subject, "sessions", "subject", row.id)
        content_preview = last_content[:120] if last_content else None
        sessions.append({
            "id": str(row.id),
            "subject": subject or (title_from_message(first_content) if first_content else None),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "message_count": row.message_count,
            "last_message": content_preview,
            "last_role": row.last_role,
        })

    return {"sessions": sessions}


@router.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    """Return a session with all its messages."""
    from app.models.models import User

    auth_id = _auth_id_from_token(credentials)
    user = await _get_user_or_404(auth_id, db)

    sess = (
        await db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user.id)
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    msgs = (
        await db.execute(
            select(Message)
            .where(Message.session_id == sess.id)
            .order_by(Message.created_at.asc())
        )
    ).scalars().all()

    return {
        "id": str(sess.id),
        "subject": sess.subject or next((title_from_message(m.content) for m in msgs if m.role == "user"), None),
        "started_at": sess.started_at.isoformat() if sess.started_at else None,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@router.patch("/chat/sessions/{session_id}")
async def rename_session(
    session_id: uuid.UUID,
    body: RenameSessionRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    auth_id = _auth_id_from_token(credentials)
    user = await _get_user_or_404(auth_id, db)
    title = " ".join(body.title.split())
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Title cannot be empty")

    sess = (
        await db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user.id)
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    sess.subject = title
    await db.commit()
    return {"id": str(sess.id), "subject": title}


@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session and all its messages."""
    from app.models.models import User

    auth_id = _auth_id_from_token(credentials)
    user = await _get_user_or_404(auth_id, db)

    sess = (
        await db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user.id)
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    # Delete messages first, then session
    await db.execute(
        Message.__table__.delete().where(Message.session_id == sess.id)
    )
    await db.delete(sess)
    await db.commit()

    return {"deleted": True}
