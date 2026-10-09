"""Teach v2 — Postgres turn-engine endpoint (Chunk 2).

POST /teach/v2/message (SSE): auth -> session -> run_turn -> one SSE data
event with `delta` plus [DONE]. Same frontend contract as /chat/message.
Old paths untouched.
"""

import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.users import _auth_id_from_token
from app.core.db import get_db
from app.models.models import Message, Session, User
from app.services.cost_firewall import MESSAGES as _LIMIT_MSGS, check_turn_budget
from app.services.turn_engine import route_turn, write_turn
from app.services.chat_titles import title_from_message

logger = logging.getLogger("uvicorn.error.pixie.teach")

router = APIRouter(tags=["teach-v2"])
bearer = HTTPBearer(auto_error=False)


class TeachV2Request(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: uuid.UUID | None = None


async def _call_llm_json(system: str, user: str, max_tokens: int = 600) -> dict:
    from app.services.llm_registry import get_provider

    provider = get_provider("chat")
    provider_started = time.perf_counter()
    result = await provider.complete(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_mode=True,
        temperature=0.4,
        max_tokens=max_tokens,
    )
    logger.info("learn_provider_complete seconds=%.3f", time.perf_counter()-provider_started)
    if result.get("finish_reason") == "length":
        raise ValueError("Teaching provider output truncated")
    content = result.get("content", "")
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(cleaned)


@router.post("/teach/v2/message")
async def teach_v2_message(
    body: TeachV2Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    request_started = time.perf_counter()
    auth_id = _auth_id_from_token(credentials)
    user = (
        await db.execute(select(User).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        async def _no_user():
            yield f"data: {json.dumps({'error': 'User not provisioned'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_user(), media_type="text/event-stream")

    # Cost firewall: taught turns burn provider tokens. Check budget before
    # any session/message writes — a limited turn writes nothing.
    _budget = await check_turn_budget(db, user)
    if _budget != "ok":
        _msg = _LIMIT_MSGS[_budget]
        async def _limited(msg=_msg):
            yield f"data: {json.dumps({'delta': msg, 'event': 'limit', 'limited': True})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_limited(), media_type="text/event-stream")

    if body.session_id is not None:
        sess = (
            await db.execute(
                select(Session).where(
                    Session.id == body.session_id, Session.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if sess is None:
            async def _no_sess():
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(_no_sess(), media_type="text/event-stream")
    else:
        sess = Session(user_id=user.id, subject=title_from_message(body.message))
        db.add(sess)
        await db.flush()
        # Mirror in Honcho so message signals have a home. Best-effort.
        try:
            from app.services.honcho_client import HonchoClient

            await HonchoClient().create_session(
                user.honcho_peer_id, str(sess.id)
            )
        except Exception:
            pass

    db.add(Message(session_id=sess.id, user_id=user.id, role="user", content=body.message))
    await db.commit()

    async def _stream():
        route_started = time.perf_counter()
        yield f"data: {json.dumps({'session_id': str(sess.id)})}\n\n"
        try:
            routed = await route_turn(
                db, user.id, body.message, sess.id,
                grade_level=user.grade_level,
                call_llm_json=_call_llm_json,
            )
        except Exception as e:
            logger.error("teach v2 route failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': 'An error occurred. Please try again.'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        route_seconds = time.perf_counter()-route_started
        if routed.get("route") is None:
            # Instant answer: greeting, redirect, escalate. No writer.
            payload = routed["payload"]
            db.add(Message(
                session_id=sess.id, user_id=user.id,
                role="assistant", content=payload.get("delta", ""),
            ))
            await db.commit()
            yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"
            return
        # Verdict first so the student sees feedback in seconds.
        early = (routed["route"] or {}).get("early_delta")
        if early:
            early = early + "\n\n"
            yield f"data: {json.dumps({'delta': early, 'structured': True, 'event': 'verdict'})}\n\n"
        writer_started = time.perf_counter()
        try:
            payload = await write_turn(
                db, user.id, routed["route"], call_llm_json=_call_llm_json,
            )
        except Exception as e:
            logger.error("teach v2 write failed: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': 'An error occurred. Please try again.'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        logger.info("learn_turn route_seconds=%.3f writer_seconds=%.3f total_seconds=%.3f", route_seconds, time.perf_counter()-writer_started, time.perf_counter()-request_started)
        persisted_reply = (early or "") + payload.get("delta", "")
        db.add(Message(
            session_id=sess.id, user_id=user.id,
            role="assistant", content=persisted_reply,
        ))
        await db.commit()
        # Chunk 5: learning happens after the answer, never before it.
        from app.services.post_turn_v2 import launch_lesson_post_turn

        if payload.get("event") != "unavailable":
            launch_lesson_post_turn(
                user.id, sess.id, body.message, persisted_reply,
                grade_level=user.grade_level or "",
            )
        yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
