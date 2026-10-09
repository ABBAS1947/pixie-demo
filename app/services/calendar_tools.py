"""Calendar tools for the pixie's chat — DeepSeek function calling.

Gives the AI real read/write access to the user's calendar (MASTER-CALENDAR
"conversation" source). Every tool is user-scoped: identity comes from the
JWT-resolved user, never from the model's arguments.

Tools exposed to the model:
- list_deadlines: read upcoming deadlines (optionally by date range)
- create_deadline: add a deadline from conversation (confirmed=True — the
  student explicitly asked for it, unlike passive post-turn extraction)
- update_deadline: reschedule / retitle / confirm
- delete_deadline: remove
"""

import json  # noqa: F401 — callers serialize tool results with json.dumps
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Deadline, User

# OpenAI/DeepSeek function-calling schemas. Keep argument names in the same
# snake_case as the REST API so the executor maps 1:1.
CALENDAR_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_deadlines",
            "description": "List the student's deadlines, optionally filtered by date range. Use for 'what's due', 'when is my exam', calendar questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "Only deadlines within this many days from now. Default 30."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_deadline",
            "description": "Add a deadline the student explicitly asked for. Confirmed immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title, e.g. 'Chemistry Unit 3 exam'."},
                    "due_at": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-09-20T09:00:00Z."},
                    "kind": {"type": "string", "enum": ["assignment", "exam", "project"], "description": "Default assignment."},
                    "pace_plan": {"type": "string", "description": "Optional one-line study plan."},
                },
                "required": ["title", "due_at"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_deadline",
            "description": "Update an existing deadline: reschedule (due_at), retitle, change kind, or confirm. Find the id with list_deadlines first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Deadline id (UUID)."},
                    "title": {"type": "string"},
                    "due_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "kind": {"type": "string", "enum": ["assignment", "exam", "project"]},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_deadline",
            "description": "Delete a deadline the student asked to remove. Find the id with list_deadlines first.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "Deadline id (UUID)."}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
    },
]


def _deadline_summary(d: Deadline) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "title": d.title,
        "due_at": d.due_at.isoformat(),
        "kind": d.kind,
        "status": d.status,
        "source": d.source,
        "confirmed": d.confirmed,
        "pace_plan": d.pace_plan,
        "synced_to_google": d.synced_to_google,
    }


async def _list_deadlines(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    days = max(1, min(int(args.get("days_ahead", 30)), 365))
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(Deadline)
            .where(Deadline.user_id == user.id, Deadline.due_at >= now)
            .order_by(Deadline.due_at.asc())
            .limit(50)
        )
    ).scalars().all()
    upcoming = [d for d in rows if (d.due_at - now).days <= days]
    return {
        "count": len(upcoming),
        "deadlines": [_deadline_summary(d) for d in upcoming],
    }


async def _create_deadline(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    due_raw = args.get("due_at")
    if not title:
        raise ValueError("title is required and must be non-empty")
    if not due_raw:
        raise ValueError("due_at is required (ISO 8601 datetime)")
    try:
        due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"due_at is not a valid ISO datetime: {due_raw}")
    kind = args.get("kind", "assignment")
    if kind not in ("assignment", "exam", "project"):
        raise ValueError("kind must be one of: assignment, exam, project")
    d = Deadline(
        user_id=user.id,
        title=title[:500],
        due_at=due,
        kind=kind,
        source="conversation",
        confirmed=True,
        pace_plan=str(args["pace_plan"])[:2000] if args.get("pace_plan") else None,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return {"created": _deadline_summary(d)}


async def _update_deadline(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    from uuid import UUID

    try:
        did = UUID(str(args["id"]))
    except (KeyError, ValueError):
        raise ValueError("id is required and must be a valid UUID")
    d = (
        await db.execute(select(Deadline).where(Deadline.id == did, Deadline.user_id == user.id))
    ).scalar_one_or_none()
    if d is None:
        raise ValueError("deadline not found")
    if "title" in args and args["title"] is not None:
        d.title = str(args["title"]).strip()[:500]
    if "due_at" in args and args["due_at"]:
        try:
            d.due_at = datetime.fromisoformat(str(args["due_at"]).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"due_at is not a valid ISO datetime: {args['due_at']}")
    if "kind" in args and args["kind"]:
        if args["kind"] not in ("assignment", "exam", "project"):
            raise ValueError("kind must be one of: assignment, exam, project")
        d.kind = args["kind"]
    if "confirmed" in args and isinstance(args["confirmed"], bool):
        d.confirmed = args["confirmed"]
    await db.commit()
    await db.refresh(d)
    return {"updated": _deadline_summary(d)}


async def _delete_deadline(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    from uuid import UUID

    try:
        did = UUID(str(args["id"]))
    except (KeyError, ValueError):
        raise ValueError("id is required and must be a valid UUID")
    d = (
        await db.execute(select(Deadline).where(Deadline.id == did, Deadline.user_id == user.id))
    ).scalar_one_or_none()
    if d is None:
        raise ValueError("deadline not found")
    await db.delete(d)
    await db.commit()
    return {"deleted": str(did)}


_TOOL_EXECUTORS = {
    "list_deadlines": _list_deadlines,
    "create_deadline": _create_deadline,
    "update_deadline": _update_deadline,
    "delete_deadline": _delete_deadline,
}


async def execute_calendar_tool(
    db: AsyncSession, user: User, name: str, arguments: dict
) -> dict[str, Any]:
    """Run a tool; ValueError becomes a structured error the model can read."""
    fn = _TOOL_EXECUTORS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(db, user, arguments or {})
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 — model-facing guard
        return {"error": f"tool failed: {e}"}


async def upcoming_deadlines_block(db: AsyncSession, user: User, limit: int = 8) -> str:
    """Compact system-prompt snapshot so the AI can answer date questions
    without a tool round-trip. The tools give the full picture on demand."""
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(Deadline)
            .where(Deadline.user_id == user.id, Deadline.due_at >= now)
            .order_by(Deadline.due_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return ""
    lines = [
        f"- {d.title} [{d.kind}] due {d.due_at.strftime('%Y-%m-%d %H:%M %Z')}"
        + (" (unconfirmed)" if not d.confirmed else "")
        for d in rows
    ]
    return (
        "The student's upcoming deadlines (from the calendar):\n"
        + "\n".join(lines)
        + "\nUse the calendar tools for details or changes."
    )


# ─── Notes tools ──────────────────────────────────────────────────────────────

NOTES_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Save a note from the conversation. Use this when you teach something worth keeping, when the student asks you to save info, or when you summarize a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title for the note, e.g. 'Photosynthesis overview'."},
                    "content": {"type": "string", "description": "The note content in markdown."},
                },
                "required": ["title", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "List all saved notes. Use this when the student asks about their notes, wants to see what's saved, or asks 'what notes do I have'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Search through saved notes by topic or keyword. Use this when the student asks about a specific topic, wants to find notes about something, or asks 'do I have notes about X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query — topic, keyword, or question to find matching notes."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": "Read the full content of a specific note. Use this when the student wants to review a saved note, asks to see a note's content, or says 'show me that note'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "The note ID to read."}
                },
                "required": ["note_id"],
            },
        },
    },
]


async def _create_note(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    content = str(args.get("content", "")).strip()
    if not title:
        raise ValueError("title is required")
    if not content:
        raise ValueError("content is required")

    try:
        from app.services.ollama_client import embed_text as _embed
        embedding = await _embed(f"{title}\n{content}")
    except Exception:
        embedding = None

    try:
        from app.services.vault_service import write_note_file
        vault_path = await write_note_file(user, title, content)
    except Exception:
        vault_path = None

    from app.models.models import Note as NoteModel
    note = NoteModel(
        user_id=user.id,
        title=title[:500],
        content=content[:20000],
        embedding=embedding,
        vault_path=vault_path,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return {"created": {"id": str(note.id), "title": note.title}}


async def _list_notes(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    from app.models.models import Note as NoteModel
    result = await db.execute(
        select(NoteModel.id, NoteModel.title, NoteModel.created_at)
        .where(NoteModel.user_id == user.id)
        .order_by(NoteModel.created_at.desc())
        .limit(50)
    )
    notes = [
        {"id": str(r.id), "title": r.title, "created": r.created_at.isoformat()}
        for r in result.all()
    ]
    return {"notes": notes, "count": len(notes)}


async def _search_notes(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    query = args.get("query", "").strip()
    if not query:
        return {"error": "query is required"}

    from app.models.models import Note as NoteModel

    # Try semantic search first via pgvector
    try:
        from app.services.ollama_client import embed_text as _embed
        from sqlalchemy import func

        q_embedding = await _embed(query)
        vec = Vector(q_embedding)  # type: ignore[arg-type]
        result = await db.execute(
            select(NoteModel.id, NoteModel.title, NoteModel.content, NoteModel.created_at)
            .where(NoteModel.user_id == user.id, NoteModel.embedding.isnot(None))
            .order_by(NoteModel.embedding.cosine_distance(vec))
            .limit(5)
        )
        notes = [
            {
                "id": str(r.id),
                "title": r.title,
                "preview": r.content[:300],
                "created": r.created_at.isoformat(),
            }
            for r in result.all()
        ]
        return {"notes": notes, "count": len(notes)}
    except Exception:
        # Fallback to simple text search
        result = await db.execute(
            select(NoteModel.id, NoteModel.title, NoteModel.content, NoteModel.created_at)
            .where(NoteModel.user_id == user.id, NoteModel.content.ilike(f"%{query}%"))
            .order_by(NoteModel.created_at.desc())
            .limit(5)
        )
        notes = [
            {
                "id": str(r.id),
                "title": r.title,
                "preview": r.content[:300],
                "created": r.created_at.isoformat(),
            }
            for r in result.all()
        ]
        return {"notes": notes, "count": len(notes)}


async def _read_note(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    from uuid import UUID

    note_id = args.get("note_id", "")
    if not note_id:
        return {"error": "note_id is required"}

    try:
        nid = UUID(note_id)
    except Exception:
        return {"error": "invalid note_id format"}

    from app.models.models import Note as NoteModel

    result = await db.execute(
        select(NoteModel).where(NoteModel.id == nid, NoteModel.user_id == user.id)
    )
    note = result.scalar_one_or_none()
    if not note:
        return {"error": "note not found"}
    return {
        "id": str(note.id),
        "title": note.title,
        "content": note.content,
        "created": note.created_at.isoformat(),
    }


_NOTES_EXECUTORS = {
    "create_note": _create_note,
    "list_notes": _list_notes,
    "search_notes": _search_notes,
    "read_note": _read_note,
}


async def execute_notes_tool(
    db: AsyncSession, user: User, name: str, arguments: dict
) -> dict[str, Any]:
    fn = _NOTES_EXECUTORS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(db, user, arguments or {})
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"tool failed: {e}"}


# ─── Files tools ──────────────────────────────────────────────────────────────

FILES_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all uploaded files. Use this when the student asks about their files, wants to see what's uploaded, or asks 'what files do I have'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content or metadata of a specific uploaded file. For text files returns the extracted content; for PDFs/images returns metadata and summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "The file ID to read."}
                },
                "required": ["file_id"],
            },
        },
    },
]


async def _list_files(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    from app.models.models import File as FileModel

    result = await db.execute(
        select(FileModel)
        .where(FileModel.user_id == user.id)
        .order_by(FileModel.uploaded_at.desc())
        .limit(50)
    )
    files = [
        {
            "id": str(r.id),
            "name": r.original_name,
            "type": r.file_type,
            "size": r.file_size,
            "mime": r.mime_type,
            "status": r.status,
            "uploaded": r.uploaded_at.isoformat(),
        }
        for r in result.scalars().all()
    ]
    return {"files": files, "count": len(files)}


async def _read_file(db: AsyncSession, user: User, args: dict) -> dict[str, Any]:
    from uuid import UUID

    file_id = args.get("file_id", "")
    if not file_id:
        return {"error": "file_id is required"}

    try:
        fid = UUID(file_id)
    except Exception:
        return {"error": "invalid file_id format"}

    from app.models.models import File as FileModel

    result = await db.execute(
        select(FileModel).where(FileModel.id == fid, FileModel.user_id == user.id)
    )
    f = result.scalar_one_or_none()
    if not f:
        return {"error": "file not found"}

    # Return extracted text if available, otherwise metadata
    base = {
        "id": str(f.id),
        "name": f.original_name,
        "type": f.file_type,
        "size": f.file_size,
        "mime": f.mime_type,
        "status": f.status,
        "uploaded": f.uploaded_at.isoformat(),
    }

    if f.extracted_text:
        base["content"] = f.extracted_text[:10000]
    if f.title:
        base["title"] = f.title
    if f.description:
        base["description"] = f.description
    if f.error_message:
        base["error"] = f.error_message

    return base


_FILES_EXECUTORS = {
    "list_files": _list_files,
    "read_file": _read_file,
}


async def execute_files_tool(
    db: AsyncSession, user: User, name: str, arguments: dict
) -> dict[str, Any]:
    fn = _FILES_EXECUTORS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(db, user, arguments or {})
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"tool failed: {e}"}
