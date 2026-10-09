"""Frontend Review contract, owner-scoped with replayable lifecycle mutations."""
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from datetime import datetime,timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.models import User,Note
from app.models.review_models import QuizSession, Concept, ConceptMastery
from app.services import review_sessions as service
from app.services.review_contract import PrepareRequest, ReviewAction, MODES, LENGTHS, POLICY_VERSION

router=APIRouter(prefix='/review',tags=['review-sessions'])
class PreferencesRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    penalties_enabled:bool|None=None
    external_processing_consent:bool|None=None
    reduced_motion:bool|None=None
    reduced_text:bool|None=None
class SourceReference(BaseModel):
    note_id:uuid.UUID
    title:str
    hash:str
    quote:str|None=None
class SourceScope(BaseModel):
    id:uuid.UUID
    title:str
    hash:str
class ItemResult(BaseModel):
    kind:Literal['assessment','practice','skipped']
    score:float|None
    correct:bool|None
    independence:Literal['independent','supported','unknown']
    judgment:Literal['correct','partially_correct','incorrect','unassessable']|None=None
    feedback:str|None=None
    response:str|None=None
    attempt_id:uuid.UUID|None=None
    evidence_id:uuid.UUID|None=None
    rating:Literal['knew_it','almost','need_practice']|None=None
class PresentedItem(BaseModel):
    id:uuid.UUID
    position:int
    concept_id:uuid.UUID
    format:Literal['mcq','true_false','short_answer','reveal_card']
    question:str
    options:list[str]
    source:SourceReference
    supported:bool
    revealed:bool
    result:ItemResult|None
    retries:list[ItemResult]
    clarification:str|None
    hint:str|None=None
    answer:str|None=None
    explanation:str|None=None
    rubric:str|None=None
class Progress(BaseModel):
    finished:int
    total:int
    assessed:int
    independent:int
    correct:int
    skipped:int
    practice:int
class XPPolicy(BaseModel):
    policy_version:str
    max_xp:int
    loss_cap:int
    item_cap:int
    poor_score_threshold:float
    penalties_enabled:bool
class XPPreview(BaseModel):
    requested_delta:int
    delta:int
    reason:str
class XPReceipt(XPPreview):
    id:uuid.UUID
    quiz_id:uuid.UUID
    user_id:uuid.UUID
    policy_version:str
    balance_before:int
    balance_after:int
    created_at:str
class PreparationStatus(BaseModel):
    status:Literal['pending','running','done','failed','cancelled']
    attempts:int
    last_error:str|None
class NextStep(BaseModel):
    surface:Literal['chat_learn']
    concept_ids:list[uuid.UUID]
class SessionResponse(BaseModel):
    id:uuid.UUID
    status:str
    state_version:int
    mode:str
    length:str
    cursor:int
    created_at:str
    started_at:str|None
    completed_at:str|None
    policy_version:str
    selection_policy:str
    requested_count:int
    actual_count:int
    limitations:list[str]
    preparation:PreparationStatus|None
    sources:list[SourceScope]
    progress:Progress
    score:float|None
    items:list[PresentedItem]
    available_actions:list[str]
    xp_policy:XPPolicy
    abandon_preview:XPPreview
    xp_receipt:XPReceipt|None
    next_step:NextStep|None

async def mutation(db,call):
    try:result=await call;await db.commit();return result
    except service.ReviewError as exc:await db.rollback();raise HTTPException(exc.status,detail={'code':exc.code})
    except Exception:await db.rollback();raise

@router.get('/config')
async def config(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return {'policy_version':POLICY_VERSION,'modes':MODES,'lengths':LENGTHS,'defaults':{'mode':'smart_mix','length':'spark','selection_policy':'priority'},'preferences':await service.preferences(db,user.id),'external_processing':{'provider':'configured model provider (currently DeepSeek)','payload':'Selected note text for generation/validation; question, rubric, source quote and student answer for semantic grading.','requires_explicit_consent':True},'xp_rules':{'poor_score_threshold':.4,'exemptions':['pause','no_assessable_answers','supported_practice','service_failure','unassessable','browser_close'],'settlement':'once_per_session','balance_floor':0}}

@router.put('/preferences')
async def prefs(request:PreferencesRequest,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await mutation(db,service.set_preferences(db,user.id,request))

@router.get('/home')
async def home(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    resumable=(await db.execute(select(QuizSession).where(QuizSession.user_id==user.id,QuizSession.review_contract.is_not(None),QuizSession.status.in_(['preparing','prepared','active','paused','failed'])).order_by(QuizSession.created_at.desc()).limit(4))).scalars().all()
    notes=(await db.execute(select(Note).where(Note.user_id==user.id).order_by(Note.created_at.desc(),Note.id).limit(30))).scalars().all()
    concepts=(await db.execute(select(Concept,ConceptMastery).outerjoin(ConceptMastery,(ConceptMastery.concept_id==Concept.id)&(ConceptMastery.user_id==user.id)).where(Concept.user_id==user.id,Concept.source_note_id.is_not(None)).order_by(ConceptMastery.due_at.asc().nullsfirst(),ConceptMastery.confidence.asc().nullsfirst(),Concept.id).limit(20))).all()
    stamp=datetime.now(timezone.utc)
    return {'preferences':await service.preferences(db,user.id),'resumable':[await service.view(db,q) for q in resumable],'materials':[{'id':str(n.id),'title':n.title} for n in notes],'material_limit':30,'suggested_concepts':[{'id':str(c.id),'label':c.label,'note_id':str(c.source_note_id),'reason':'new' if not m or not m.signal_count else 'due' if m.due_at and m.due_at<=stamp else 'needs_practice' if float(m.confidence)<.6 else 'reinforcement','independent_signal_count':m.signal_count if m else 0} for c,m in concepts],'adaptation_basis':'Existing source-linked concept evidence and due dates; no inferred disability or learning-style diagnosis.'}

@router.post('/sessions',status_code=202,response_model=SessionResponse,response_model_exclude_unset=True)
async def prepare(request:PrepareRequest,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await mutation(db,service.prepare(db,user.id,request))

@router.get('/sessions',response_model=list[SessionResponse],response_model_exclude_unset=True)
async def history(limit:int=20,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    if not 1<=limit<=50:raise HTTPException(422,'limit must be 1..50')
    rows=(await db.execute(select(QuizSession).where(QuizSession.user_id==user.id,QuizSession.review_contract.is_not(None)).order_by(QuizSession.created_at.desc(),QuizSession.id).limit(limit))).scalars().all()
    return [await service.view(db,q) for q in rows]

@router.get('/sessions/{ident}',response_model=SessionResponse,response_model_exclude_unset=True)
async def detail(ident:uuid.UUID,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    try:return await service.view(db,await service.owned(db,user.id,ident))
    except service.ReviewError as exc:raise HTTPException(exc.status,detail={'code':exc.code})

@router.get('/sessions/{ident}/requests/{key}',response_model=SessionResponse,response_model_exclude_unset=True)
async def request_status(ident:uuid.UUID,key:uuid.UUID,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    try:
        result=await service.replay(db,user.id,ident,key)
        if result is None:raise service.ReviewError('request_not_committed',404)
        return result
    except service.ReviewError as exc:raise HTTPException(exc.status,detail={'code':exc.code})

@router.post('/sessions/{ident}/actions',response_model=SessionResponse,response_model_exclude_unset=True)
async def action(ident:uuid.UUID,request:ReviewAction,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await mutation(db,service.act(db,user.id,ident,request))
