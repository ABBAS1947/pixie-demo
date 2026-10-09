"""Transactional shared learning service. PostgreSQL is the state authority.

Published content is pinned when a task is issued. Request replays are keyed,
fingerprinted, owner-scoped and serialized by an activity row lock. No provider
or optional memory call is made while holding locks. All writes use caller tx.
"""
import hashlib
import json
import uuid
from sqlalchemy import text
from app.services.learning_contract import TaskContent, grade

EVIDENCE_NAMESPACE = uuid.UUID("6d6f2a62-6ee4-4d8d-bf07-07f6ac2f7e40")


async def record_external_evidence(
    db, *, user_id, source_type, source_id, surface, label, response,
    judgment, purpose="independent", independence="independent", content_hash="", skill_id=None,
    skill_code=None, skill_version=None, external_content=None,
):
    """Reserved external anchors preserve real provenance, never reusable fake keys."""
    if judgment not in ("correct","incorrect"): raise ValueError("external evidence must be graded")
    skill_id=skill_id or source_id
    mapping=await row(db,"SELECT * FROM learning_skill_mappings WHERE source_type=:type AND source_id=:source",
        {"type":"review_concept" if source_type.startswith("review") else "learn_chunk","source":skill_id})
    code=skill_code or (mapping["skill_code"] if mapping else f"{source_type}:{skill_id}")
    version=skill_version or (mapping["skill_version"] if mapping else 1)
    if mapping and mapping["status"]=="rejected": raise ValueError("rejected skill mapping")
    await db.execute(text("""INSERT INTO learning_skills(code,version,objective,published,approval)
        VALUES(:code,:version,:label,false,NULL) ON CONFLICT(code,version) DO NOTHING"""),
        {"code":code,"version":version,"label":label[:1000]})
    # Legacy bridges propose identities; answers cannot approve or overwrite curriculum mappings.
    await db.execute(text("""INSERT INTO learning_skill_mappings(id,source_type,source_id,skill_code,skill_version,status,rationale)
        VALUES(:id,:type,:source,:code,:version,'proposed','Legacy outcome identity; requires source validation.')
        ON CONFLICT(source_type,source_id) DO NOTHING"""),
        {"id":uuid.uuid4(),"type":"review_concept" if source_type.startswith("review") else "learn_chunk",
         "source":skill_id,"code":code,"version":version})
    anchor=uuid.uuid5(EVIDENCE_NAMESPACE,f"{source_type}:event:{source_id}")
    actual=external_content or {}
    content=TaskContent(title=f"Evidence: {label[:120]}",instruction="Reserved record; evaluate only on the originating surface.",
        question=actual.get("question","Externally evaluated response"),response_kind="external",
        answer=actual.get("answer","No reusable answer key"),explanation=actual.get("explanation","See originating surface feedback."),
        hint=actual.get("hint","Return to the originating activity."),family=actual.get("family",f"{source_type}:{source_id}"),
        language="en",assessed_construct=label[:500],approval=actual.get("approval","legacy-unvalidated"),purpose=purpose)
    values={"id":anchor,"user":user_id,"code":code,"version":version,"surface":surface,
        "content":content.model_dump_json(),"supported":independence!="independent","purpose":purpose,
        "judgment":judgment,"independence":independence,"response":response or "",
        "hash":content_hash if len(content_hash)==64 else fingerprint(actual or content.model_dump())}
    await db.execute(text("""INSERT INTO learning_items(id,skill_code,skill_version,content,sequence,published,reserved)
        VALUES(:id,:code,:version,CAST(:content AS jsonb),0,false,true) ON CONFLICT(id) DO NOTHING"""),values)
    await db.execute(text("""INSERT INTO learning_activities(id,user_id,skill_code,skill_version,surface,status)
        VALUES(:id,:user,:code,:version,:surface,'complete') ON CONFLICT(id) DO NOTHING"""),values)
    await db.execute(text("""INSERT INTO learning_tasks(id,activity_id,user_id,item_id,content,supported,status)
        VALUES(:id,:id,:user,:id,CAST(:content AS jsonb),:supported,'assessed') ON CONFLICT(id) DO NOTHING"""),values)
    await db.execute(text("""INSERT INTO learning_evidence(id,task_id,user_id,skill_code,skill_version,surface,purpose,judgment,independence,response,content_hash)
        VALUES(:id,:id,:user,:code,:version,:surface,:purpose,:judgment,:independence,:response,:hash)
        ON CONFLICT(task_id) DO NOTHING"""),values)
    await db.execute(text("""INSERT INTO learning_jobs(id,event_id,kind) VALUES(:job,:event,'evidence_summary')
        ON CONFLICT(event_id,kind) DO NOTHING"""),{"job":uuid.uuid5(anchor,"summary"),"event":anchor})
    return anchor

class LearningError(Exception):
    def __init__(self, code, status=409): self.code,self.status=code,status

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

async def row(db,sql,values):
    return (await db.execute(text(sql),values)).mappings().first()

async def activity(db,user,ident,lock=False):
    value=await row(db,'SELECT * FROM learning_activities WHERE id=:id AND user_id=:user'+(' FOR UPDATE' if lock else ''),{'id':ident,'user':user})
    if value is None: raise LearningError('activity_not_found',404)
    return value

async def current(db,a):
    if a['task_id'] is None: return None
    return await row(db,'SELECT * FROM learning_tasks WHERE id=:id AND activity_id=:activity',{'id':a['task_id'],'activity':a['id']})

async def view(db,a):
    t=await current(db,a)
    return {'activity_id':str(a['id']),'surface':a['surface'],'skill_code':a['skill_code'],'skill_version':a['skill_version'],'version':a['version'],'status':a['status'],'task':None if not t else {'id':str(t['id']),'status':t['status'],'supported':t['supported'],'content':TaskContent.model_validate(t['content']).presentation(),'feedback':t['feedback']},'actions':[] if a['status']=='complete' else ['answer','help','pause','resume','continue']}

async def issue(db,a):
    item=await row(db,"""SELECT * FROM learning_items i WHERE skill_code=:skill AND skill_version=:version
      AND published AND NOT reserved AND (:surface='chat_learn' OR (content->>'purpose') IN ('independent','delayed'))
      AND NOT EXISTS (SELECT 1 FROM learning_tasks t WHERE t.user_id=:user AND t.item_id=i.id)
      AND ((content->>'purpose')!='delayed' OR EXISTS(SELECT 1 FROM learning_evidence e
        WHERE e.user_id=:user AND e.skill_code=i.skill_code AND e.skill_version=i.skill_version
        AND e.independence='independent' AND e.judgment='correct'
        AND e.created_at<=now()-interval '1 second'*CAST(i.content->>'minimum_delay_seconds' AS integer)))
      ORDER BY sequence,id LIMIT 1""",{'skill':a['skill_code'],'version':a['skill_version'],'surface':a['surface'],'user':a['user_id']})
    if not item:
        await db.execute(text("UPDATE learning_activities SET task_id=NULL,status='complete' WHERE id=:id"),{'id':a['id']})
        return
    content=TaskContent.model_validate(item['content'])
    prior=None
    if content.purpose=='delayed':
        prior=await row(db,"""SELECT id FROM learning_evidence WHERE user_id=:user AND skill_code=:skill AND skill_version=:version
          AND independence='independent' AND judgment='correct'
          AND created_at<=now()-interval '1 second'*:delay ORDER BY created_at DESC,id LIMIT 1""",
          {'user':a['user_id'],'skill':a['skill_code'],'version':a['skill_version'],'delay':content.minimum_delay_seconds})
        if prior is None: raise LearningError('delayed_evidence_not_eligible',422)
    ident=uuid.uuid4()
    await db.execute(text("""INSERT INTO learning_tasks(id,activity_id,user_id,item_id,content,supported,prior_event_id)
      VALUES(:id,:activity,:user,:item,CAST(:content AS jsonb),:support,:prior)"""),{'id':ident,'activity':a['id'],'user':a['user_id'],'item':item['id'],'content':content.model_dump_json(),'support':content.purpose=='practice','prior':prior['id'] if prior else None})
    await db.execute(text("UPDATE learning_activities SET task_id=:task WHERE id=:id"),{'task':ident,'id':a['id']})

async def start(db,user,key,skill,version,surface):
    params={'skill':skill,'version':version,'surface':surface};digest=fingerprint(params)
    # User-row lock serializes starts/replays for this learner; different learners proceed independently.
    await db.execute(text('SELECT id FROM users WHERE id=:id FOR UPDATE'),{'id':user})
    prior=await row(db,'SELECT * FROM learning_starts WHERE user_id=:user AND request_id=:key',{'user':user,'key':key})
    if prior:
        if prior['fingerprint']!=digest: raise LearningError('idempotency_conflict')
        return prior['result']
    skillrow=await row(db,'SELECT * FROM learning_skills WHERE code=:skill AND version=:version AND published',params)
    if not skillrow: raise LearningError('approved_skill_not_found',404)
    ident=uuid.uuid4()
    await db.execute(text('INSERT INTO learning_activities(id,user_id,skill_code,skill_version,surface) VALUES(:id,:user,:skill,:version,:surface)'),dict(params,id=ident,user=user))
    a=await activity(db,user,ident);await issue(db,a);a=await activity(db,user,ident);result=await view(db,a)
    if result['task'] is None: raise LearningError('approved_items_unavailable',422)
    await db.execute(text('INSERT INTO learning_starts(user_id,request_id,fingerprint,result) VALUES(:user,:key,:digest,CAST(:result AS jsonb))'),{'user':user,'key':key,'digest':digest,'result':json.dumps(result)})
    return result

async def act(db,user,ident,request):
    a=await activity(db,user,ident,True)
    args=request.model_dump(mode='json');digest=fingerprint(args)
    prior=await row(db,'SELECT * FROM learning_submissions WHERE activity_id=:id AND request_id=:key',{'id':ident,'key':request.request_id})
    if prior:
        if prior['fingerprint']!=digest: raise LearningError('idempotency_conflict')
        return prior['result']
    if a['version']!=request.version: raise LearningError('stale_activity')
    t=await current(db,a)
    if t is None: raise LearningError('activity_complete')
    if str(t['id'])!=str(request.task_id): raise LearningError('stale_task')
    content=TaskContent.model_validate(t['content']);feedback=None
    if request.action=='pause':
        await db.execute(text("UPDATE learning_activities SET status='paused' WHERE id=:id"),{'id':ident})
    elif request.action=='resume':
        await db.execute(text("UPDATE learning_activities SET status='active' WHERE id=:id"),{'id':ident})
    else:
        if a['status']!='active': raise LearningError('activity_paused')
        if request.action=='help':
            if t['status']!='awaiting': raise LearningError('task_already_assessed')
            await db.execute(text('UPDATE learning_tasks SET supported=true WHERE id=:id'),{'id':t['id']})
            feedback={'kind':'help','text':content.hint}
        elif request.action=='continue':
            if t['status']!='assessed': raise LearningError('answer_required')
            await issue(db,a)
        elif request.action=='answer':
            if t['status']!='awaiting': raise LearningError('task_already_assessed')
            judgment=grade(content,request.response)
            if judgment=='unassessable':
                feedback={'kind':'clarification','text':'Please enter an answer in the requested format, or choose Help.'}
            else:
                independence='supported' if t['supported'] or request.assistance=='supported' else request.assistance
                event=uuid.uuid4()
                feedback={'kind':judgment,'text':('Correct. ' if judgment=='correct' else 'Let us practise this step. ')+content.explanation,'independence':independence}
                await db.execute(text("""INSERT INTO learning_evidence(id,task_id,user_id,skill_code,skill_version,surface,purpose,judgment,independence,response,content_hash,prior_event_id,elapsed_seconds)
                  VALUES(:id,:task,:user,:skill,:version,:surface,:purpose,:judgment,:independence,:response,:hash,:prior,
                   CASE WHEN CAST(:prior AS uuid) IS NOT NULL THEN EXTRACT(EPOCH FROM now()-(SELECT created_at FROM learning_evidence WHERE id=:prior)) ELSE NULL END)"""),{'id':event,'task':t['id'],'user':user,'skill':a['skill_code'],'version':a['skill_version'],'surface':a['surface'],'purpose':content.purpose,'judgment':judgment,'independence':independence,'response':request.response,'hash':fingerprint(t['content']),'prior':t['prior_event_id']})
                await db.execute(text("UPDATE learning_tasks SET status='assessed',feedback=CAST(:feedback AS jsonb) WHERE id=:id"),{'id':t['id'],'feedback':json.dumps(feedback)})
                await db.execute(text("INSERT INTO learning_jobs(id,event_id,kind) VALUES(:id,:event,'evidence_summary')"),{'id':uuid.uuid4(),'event':event})
    await db.execute(text('UPDATE learning_activities SET version=version+1 WHERE id=:id'),{'id':ident})
    result=await view(db,await activity(db,user,ident))
    if feedback: result['feedback']=feedback
    await db.execute(text('INSERT INTO learning_submissions(activity_id,request_id,fingerprint,result) VALUES(:id,:key,:digest,CAST(:result AS jsonb))'),{'id':ident,'key':request.request_id,'digest':digest,'result':json.dumps(result)})
    return result
