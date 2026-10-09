"""ORM-bound field encryption with row/field AAD; raw SQL needs explicit adapters.

Hooks preserve plaintext only in authorized application memory. Flush snapshots
are restored without marking a second update; rollback restores them as well.
Bulk/raw writes to protected fields are not an alternative encryption path.
"""
import json
import uuid

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session, attributes

from app.core.config import settings
from app.services.content_crypto import seal, unseal

# Query/constraint fields intentionally remain operational metadata. Expand
# this manifest through explicit migrations, never guessing column semantics.
FIELDS = {
    "users": ("name", "grade_level"),
    "user_persona": ("resource_constraints",),
    "sessions": ("subject", "summary"),
    "messages": ("content",),
    "notes": ("title", "content", "tags"),
    "deadlines": ("title", "pace_plan"),
    "quick_items": ("content",),
    "quick_notes": ("body", "checklist"),
    "files": ("original_name", "title", "description", "subject", "extracted_text", "error_message"),
    "study_plans": ("plan_content",),
    "projects": ("title",),
    "feedback": ("message",),
    "student_facts": ("content",),
    "conversation_messages": ("content",),
    "conversation_insights": ("topics", "subjects", "concepts_covered", "difficulty_signals", "tools_used", "mood", "summary"),
    "student_profiles": ("subjects", "weak_topics", "strong_topics", "common_confusions", "preferred_tone", "learning_style"),
    "lessons": ("topic", "about", "subject"),
    "lesson_items": ("title", "body", "check_question"),
    "concepts": ("label",),
    "flashcards": ("question", "answer", "options", "review_content"),
    "quiz_items": ("review_content", "review_state"),
    "quiz_attempts": ("response", "feedback",),
}
JSON_FIELDS = {("quick_notes", "checklist"),
               *(("conversation_insights", f) for f in ("topics", "subjects", "concepts_covered", "difficulty_signals", "tools_used")),
               *(("student_profiles", f) for f in ("subjects", "weak_topics", "strong_topics", "common_confusions"))}
JSON_FIELDS.update({("flashcards", "options"), ("flashcards", "review_content"),
                    ("quiz_items", "review_content"), ("quiz_items", "review_state")})


def _identity(obj):
    table = inspect(obj).mapper.local_table.name
    if table == "users":
        owner = obj.id
    elif hasattr(obj, "user_id"):
        owner = obj.user_id
        if owner is None and "user" not in inspect(obj).unloaded:
            related = getattr(obj, "user", None)
            owner = related.id if related is not None else None
    else:
        session = inspect(obj).session
        if table == "lesson_items":
            parent = next((o for o in session.new if getattr(o, "__tablename__", None) == "lessons" and o.id == obj.lesson_id), None)
            owner = parent.user_id if parent else session.execute(text("SELECT user_id FROM lessons WHERE id=:id"), {"id": obj.lesson_id}).scalar_one()
        elif table == "quiz_items":
            owner = session.execute(text("SELECT user_id FROM quiz_sessions WHERE id=:id"), {"id": obj.quiz_session_id}).scalar_one()
        else:
            raise RuntimeError("Missing encrypted resource owner")
    resource = str(getattr(obj, "id", None) or owner)
    return table, str(owner), resource


def encrypt_value(value, *, table, field, owner, resource):
    if value is None:
        return None
    encrypted = seal(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(),
                     domain="private", owner=owner, resource=resource, field=f"{table}.{field}")
    return {"_pixie_encrypted": encrypted} if (table, field) in JSON_FIELDS else encrypted


def decrypt_value(value, *, table, field, owner, resource):
    if value is None:
        return None
    encrypted = value["_pixie_encrypted"] if (table, field) in JSON_FIELDS else value
    return json.loads(unseal(encrypted, domain="private", owner=owner,
                             resource=resource, field=f"{table}.{field}"))


def _decrypt(obj, context, attrs=None):
    if settings.content_encryption_mode != "required":
        return
    table, owner, resource = _identity(obj)
    for field in FIELDS.get(table, ()):
        if attrs is not None and field not in attrs:
            continue
        if field in inspect(obj).unloaded:
            continue
        attributes.set_committed_value(obj, field, decrypt_value(getattr(obj, field), table=table,
                                        field=field, owner=owner, resource=resource))


def _encrypt(session, context, instances):
    if settings.content_encryption_mode != "required":
        return
    snapshots = session.info.setdefault("pixie_plaintext", [])
    for obj in list(session.new) + list(session.dirty):
        table = inspect(obj).mapper.local_table.name
        if table not in FIELDS:
            continue
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()
        table, owner, resource = _identity(obj)
        if table != "users" and not session.info.get("privacy_cleanup"):
            is_new_owner = any(getattr(o, "__tablename__", None) == "users" and str(o.id) == owner for o in session.new)
            if not is_new_owner:
                state = session.execute(text("SELECT account_state,auth_id FROM users WHERE id=CAST(:id AS uuid) FOR UPDATE"), {"id": owner}).first()
                from app.services.account_lifecycle import ledger_path
                if state is None or state.account_state != "active" or ledger_path(state.auth_id).exists():
                    raise PermissionError("Account access has been revoked")
        for field in FIELDS[table]:
            if field in inspect(obj).unloaded:
                continue
            value = getattr(obj, field)
            if obj not in session.new and not inspect(obj).attrs[field].history.has_changes():
                continue
            # Resolve Python column defaults before encrypting new instances.
            if value is None and obj in session.new:
                column = inspect(obj).mapper.columns[field]
                if column.default is not None:
                    default = column.default.arg
                    value = default(None) if callable(default) else default
            if value is None:
                continue
            snapshots.append((obj, field, value))
            setattr(obj, field, encrypt_value(value, table=table, field=field, owner=owner, resource=resource))


def _restore(session, *args):
    for obj, field, value in session.info.pop("pixie_plaintext", []):
        attributes.set_committed_value(obj, field, value)


def install():
    from app.models.models import Base
    from app.models import intelligence_models  # register models before attaching hooks
    from app.models import lesson_models, review_models
    for mapper in Base.registry.mappers:
        if mapper.local_table.name in FIELDS:
            event.listen(mapper.class_, "load", _decrypt, restore_load_context=True)
            event.listen(mapper.class_, "refresh", _decrypt, restore_load_context=True)
    event.listen(Session, "before_flush", _encrypt)
    event.listen(Session, "after_flush_postexec", _restore)
    event.listen(Session, "after_soft_rollback", _restore)
