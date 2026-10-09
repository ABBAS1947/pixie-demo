"""Leased, fenced, bounded Review preparation. Safe across API processes."""
import asyncio
import logging
import uuid
from sqlalchemy import text
from app.core.db import SessionLocal
from app.models.review_models import QuizSession, QuizItem
from app.services.review_content import prepare_content

log=logging.getLogger(__name__)
KNOWN_ERRORS={'source_changed','no_source_material','no_testable_content','no_valid_questions','external_processing_consent_required','rejected_skill_mapping'}

async def run_one(factory=SessionLocal,quiz_id=None):
    token=uuid.uuid4()
    async with factory() as db:
        job=(await db.execute(text("""SELECT j.id,j.quiz_id FROM review_preparation_jobs j
          WHERE ((status='pending' AND available_at<=now()) OR (status='running' AND lease_until<=now()))
          AND (CAST(:quiz AS uuid) IS NULL OR quiz_id=:quiz)
          ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1"""),{'quiz':quiz_id})).mappings().first()
        if not job:return False
        await db.execute(text("UPDATE review_preparation_jobs SET status='running',attempts=attempts+1,lease_token=:token,lease_until=now()+interval '6 minutes' WHERE id=:id"),{'id':job['id'],'token':token})
        await db.commit()
    try:
        async with factory() as db:
            q=await db.get(QuizSession,job['quiz_id'])
            if not q or q.status!='preparing':raise ValueError('cancelled')
            from app.services.account_lifecycle import assert_user_active
            from app.services.processing_boundary import bind_actor
            await assert_user_active(db, q.user_id)
            bind_actor(q.user_id)
            from app.services.review_sessions import preferences
            prefs=await preferences(db,q.user_id)
            contract=dict(q.review_contract)
            # Consent is a user preference, not immutable question content.
            # Failed sessions created before consent was persisted can recover
            # on retry without forcing the learner through setup again.
            contract['external_processing_consent']=prefs['external_processing_consent']
            cards,limitations=await asyncio.wait_for(prepare_content(db,q.user_id,contract),300)
            # Publication locks quiz before job, as lifecycle cancellation does.
            await db.execute(text('SELECT id FROM quiz_sessions WHERE id=:id FOR UPDATE'),{'id':q.id})
            fence=(await db.execute(text("SELECT id FROM review_preparation_jobs WHERE id=:id AND status='running' AND lease_token=:token AND lease_until>now() FOR UPDATE"),{'id':job['id'],'token':token})).first()
            await db.refresh(q)
            await assert_user_active(db, q.user_id, lock=True)
            if fence is None or q.status!='preparing':await db.rollback();return True
            for position,(card,content) in enumerate(cards):
                db.add(QuizItem(quiz_session_id=q.id,flashcard_id=card.id,position=position,stage='written' if content['format']=='short_answer' else 'mcq',review_content=content,review_state={}))
            contract=dict(q.review_contract);contract['limitations']=[*contract.get('limitations',[]),*limitations]
            q.review_contract=contract;q.composition={'formats':[c['format'] for _,c in cards],'count':len(cards)};q.status='prepared';q.state_version+=1
            await db.execute(text("UPDATE review_preparation_jobs SET status='done',lease_token=NULL,lease_until=NULL,last_error=NULL WHERE id=:id"),{'id':job['id']})
            await db.commit()
    except asyncio.CancelledError:raise
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and str(exc) in KNOWN_ERRORS else 'preparation_service_unavailable'
        log.warning('Review preparation failed: %s (%s)',code,type(exc).__name__)
        async with factory() as db:
            await db.execute(text('SELECT id FROM quiz_sessions WHERE id=:id FOR UPDATE'),{'id':job['quiz_id']})
            current=(await db.execute(text("SELECT attempts FROM review_preparation_jobs WHERE id=:id AND lease_token=:token AND status='running' FOR UPDATE"),{'id':job['id'],'token':token})).mappings().first()
            if current:
                terminal=code in KNOWN_ERRORS or current['attempts']>=3
                await db.execute(text("UPDATE review_preparation_jobs SET status=:status,last_error=:error,available_at=now()+interval '10 seconds',lease_token=NULL,lease_until=NULL WHERE id=:id"),{'id':job['id'],'status':'failed' if terminal else 'pending','error':code})
                if terminal:await db.execute(text("UPDATE quiz_sessions SET status='failed',state_version=state_version+1 WHERE id=:id AND status='preparing'"),{'id':job['quiz_id']})
                await db.commit()
    return True
