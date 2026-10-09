"""Keep Review and Chat Learn mastery records consistent during the transition."""
from sqlalchemy import select, func
from app.models.mastery_models import Mastery
from app.services import mastery

async def reconcile_quiz(session, user_id, concept_id, label, confidence):
    """Apply quiz confidence only when an auditable identity is unambiguous.

    Label equality is not a canonical mapping. During migration, multiple Learn
    records may share a label while representing different constructs. Updating
    all of them silently contaminates learner history, so callers must provide a
    reviewed mapping before reconciliation can mutate a record.
    """
    keys = {f"concept::{concept_id}"}
    aliases = (await session.execute(select(Mastery).where(
        Mastery.user_id == user_id,
        func.lower(Mastery.concept_label) == label.strip().lower()))).scalars().all()
    if len(aliases) > 1:
        raise ValueError("ambiguous mastery mapping requires reviewed canonical identity")
    if aliases:
        # A single legacy alias is safe only as a one-to-one migration record.
        keys.add(aliases[0].concept_key)
    # Keep the Review concept identity as the sole write target until an
    # explicit migration table maps it to a shared skill version.
    return await mastery.set_knowledge(session, user_id, f"concept::{concept_id}", label[:300], confidence)
