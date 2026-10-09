"""Durable at-least-once worker; bounded leases and atomic idempotent summary."""
import asyncio
import json
import logging
import uuid
from sqlalchemy import text
from app.core.db import SessionLocal
from app.services.learning_service import row
logger=logging.getLogger(__name__)

async def run_one(factory=SessionLocal):
    token=uuid.uuid4()
    async with factory() as db:
        job=await row(db,"""SELECT * FROM learning_jobs WHERE
          (status='pending' AND available_at<=now()) OR (status='running' AND lease_until<now())
          ORDER BY available_at,id FOR UPDATE SKIP LOCKED LIMIT 1""",{})
        if not job: return False
        if job['attempts']>=5:
            await db.execute(text("UPDATE learning_jobs SET status='failed',last_error='retry_budget_exhausted' WHERE id=:id"),{'id':job['id']});await db.commit();return True
        await db.execute(text("UPDATE learning_jobs SET status='running',attempts=attempts+1,lease_token=:token,lease_until=now()+interval '30 seconds' WHERE id=:id"),{'id':job['id'],'token':token});await db.commit()
    try:
        async with factory() as db:
            leased=await row(db,'SELECT * FROM learning_jobs WHERE id=:id AND lease_token=:token AND lease_until>now() FOR UPDATE',{'id':job['id'],'token':token})
            if not leased: return True
            if job['kind']!='evidence_summary': raise ValueError('unsupported_job_kind')
            event=await row(db,'SELECT user_id,skill_code,skill_version FROM learning_evidence WHERE id=:id',{'id':job['event_id']})
            if not event:
                await db.execute(text("DELETE FROM learning_jobs WHERE id=:id AND lease_token=:token"), {'id':job['id'],'token':token})
                await db.commit()
                return True
            from app.services.account_lifecycle import assert_user_active
            await assert_user_active(db, event['user_id'], lock=True)
            # Serialize recomputation for a skill via user lock. Job retries never add counters twice.
            await db.execute(text('SELECT id FROM users WHERE id=:user FOR UPDATE'),{'user':event['user_id']})
            values=(await db.execute(text("SELECT judgment,independence,purpose,count(*) AS n FROM learning_evidence WHERE user_id=:user_id AND skill_code=:skill_code AND skill_version=:skill_version GROUP BY judgment,independence,purpose"),dict(event))).mappings().all()
            counts={f"{v['judgment']}:{v['independence']}:{v['purpose']}":v['n'] for v in values}
            await db.execute(text("""INSERT INTO learning_summaries(user_id,skill_code,skill_version,counts) VALUES(:user_id,:skill_code,:skill_version,CAST(:counts AS jsonb))
             ON CONFLICT(user_id,skill_code,skill_version) DO UPDATE SET counts=excluded.counts,updated_at=now()"""),dict(event,counts=json.dumps(counts)))
            await db.execute(text("UPDATE learning_jobs SET status='done',lease_token=NULL,lease_until=NULL,last_error=NULL WHERE id=:id AND lease_token=:token"),{'id':job['id'],'token':token});await db.commit()
    except Exception as exc:
        async with factory() as db:
            await db.execute(text("""UPDATE learning_jobs SET status=CASE WHEN attempts>=5 THEN 'failed' ELSE 'pending' END,
             available_at=now()+interval '10 seconds'*power(2,LEAST(attempts,5)),lease_token=NULL,lease_until=NULL,last_error=:error
             WHERE id=:id AND lease_token=:token"""),{'id':job['id'],'token':token,'error':type(exc).__name__});await db.commit()
        logger.warning('Learning job failed: %s',type(exc).__name__)
    return True

async def main():
    while True:
        if not await run_one(): await asyncio.sleep(1)

if __name__=='__main__': asyncio.run(main())
