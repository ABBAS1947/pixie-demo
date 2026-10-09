"""Shared backend API; UI ownership remains Chat Learn and Review."""
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.users import bearer, _auth_id_from_token
from app.core.db import get_db
from app.models.models import User
from app.services import learning_service as service
from app.services.learning_model import Point, estimate

router=APIRouter(prefix='/learning',tags=['shared-learning'])

class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: uuid.UUID
    skill_code: str=Field(min_length=1,max_length=160)
    skill_version: int=Field(ge=1)
    surface: Literal['chat_learn','review']

class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: uuid.UUID
    version: int=Field(ge=0)
    task_id: uuid.UUID
    action: Literal['answer','help','pause','resume','continue']
    response: str=Field(default='',max_length=2000)
    assistance: Literal['independent','supported','unknown']='unknown'

    @model_validator(mode='after')
    def answer_present(self):
        if self.action=='answer' and not self.response.strip(): raise ValueError('Answer cannot be blank')
        return self

async def owner(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:AsyncSession=Depends(get_db)):
    auth=_auth_id_from_token(credentials)
    user=(await db.execute(select(User).where(User.auth_id==auth))).scalar_one_or_none()
    if user is None: raise HTTPException(403,'User not provisioned')
    ready=(await db.execute(text("SELECT to_regclass('learning_activities') IS NOT NULL"))).scalar()
    if not ready: raise HTTPException(503,'Shared learning schema is not installed')
    return user.id

async def mutation(db,operation):
    try:
        result=await operation
        await db.commit()
        return result
    except service.LearningError as exc:
        await db.rollback()
        raise HTTPException(exc.status,exc.code) from exc
    except BaseException:
        await db.rollback()
        raise

@router.post('/activities')
async def start(body:Start,user=Depends(owner),db:AsyncSession=Depends(get_db)):
    return await mutation(db,service.start(db,user,body.request_id,body.skill_code,body.skill_version,body.surface))

@router.get('/activities/{ident}')
async def get(ident:uuid.UUID,user=Depends(owner),db:AsyncSession=Depends(get_db)):
    try: return await service.view(db,await service.activity(db,user,ident))
    except service.LearningError as exc: raise HTTPException(exc.status,exc.code) from exc

@router.post('/activities/{ident}/actions')
async def action(ident:uuid.UUID,body:Action,user=Depends(owner),db:AsyncSession=Depends(get_db)):
    return await mutation(db,service.act(db,user,ident,body))

@router.get('/activities/{ident}/submissions/{key}')
async def status(ident:uuid.UUID,key:uuid.UUID,user=Depends(owner),db:AsyncSession=Depends(get_db)):
    try: await service.activity(db,user,ident)
    except service.LearningError as exc: raise HTTPException(exc.status,exc.code) from exc
    value=await service.row(db,'SELECT result FROM learning_submissions WHERE activity_id=:id AND request_id=:key',{'id':ident,'key':key})
    return {'committed':value is not None,'result':value['result'] if value else None}

@router.get('/evidence')
async def evidence(user=Depends(owner),db:AsyncSession=Depends(get_db)):
    values=(await db.execute(text("""SELECT skill_code,skill_version,judgment,independence,purpose,count(*) AS observations,
      max(created_at) AS last_at FROM learning_evidence WHERE user_id=:user
      GROUP BY skill_code,skill_version,judgment,independence,purpose"""),{'user':user})).mappings().all()
    return {'evidence':[dict(v) for v in values],'note':'Observed evidence, not calibrated mastery or validated retention.'}

@router.get('/model-shadow')
async def model_shadow(skill_code: str = '', skill_version: int = 1, user=Depends(owner), db:AsyncSession=Depends(get_db)):
    """Phase 6 read-only estimate. Explicitly excluded from progression until gated rollout."""
    if not skill_code.strip():
        raise HTTPException(422, 'skill_code is required')
    rows = (await db.execute(text("""SELECT judgment,independence,purpose,created_at,task_id
      FROM learning_evidence WHERE user_id=:user AND skill_code=:skill AND skill_version=:version
      ORDER BY created_at,id"""), {'user':user,'skill':skill_code,'version':skill_version})).mappings().all()
    points = [Point(judgment=r['judgment'], independence=r['independence'], purpose=r['purpose'],
                    created_at=r['created_at'], task_id=str(r['task_id'])) for r in rows]
    return estimate(points)
