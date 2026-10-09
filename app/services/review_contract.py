"""Typed Review content and policies. No client controls grades, XP or evidence."""
import hashlib
import math
import re
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

POLICY_VERSION = 'review-v2.1'
CONTENT_VERSION = 'grounded-items-v1'
MODES = {'card_quiz': 'Card quiz', 'recall': 'Recall', 'smart_mix': 'Smart mix', 'browse_cards': 'Browse cards'}
LENGTHS = {
    'spark': {'label': 'Spark', 'description': 'A quick refresher', 'cap': 5, 'max_xp': 8, 'loss_cap': 1},
    'focus': {'label': 'Focus', 'description': 'Focused practice', 'cap': 10, 'max_xp': 15, 'loss_cap': 2},
    'deep_dive': {'label': 'Deep Dive', 'description': 'Broader preparation', 'cap': 20, 'max_xp': 30, 'loss_cap': 3},
}

def normalized(value):
    return ' '.join(str(value).strip().casefold().split())

def source_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    mode: Literal['card_quiz','recall','smart_mix','browse_cards'] = 'smart_mix'
    length: Literal['spark','focus','deep_dive'] = 'spark'
    note_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    concept_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    selection_policy: Literal['priority','shuffle'] = 'priority'

    @model_validator(mode='after')
    def unique_sources(self):
        if len(set(self.note_ids)) != len(self.note_ids) or len(set(self.concept_ids)) != len(self.concept_ids):
            raise ValueError('Source identifiers must be unique')
        return self

class ReviewAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    state_version: int = Field(ge=0)
    action: Literal['start','answer','help','reveal','self_rate','retry_practice','skip','next','pause','resume','abandon','complete','retry_preparation','report']
    item_id: uuid.UUID | None = None
    response: str = Field(default='', max_length=2000)
    assistance: Literal['independent','supported','unknown'] = 'independent'
    rating: Literal['knew_it','almost','need_practice'] | None = None
    reason: Literal['voluntary','unassessable','service_failure'] = 'voluntary'
    category: Literal['incorrect_answer','ambiguous','irrelevant','accessibility','other'] = 'other'
    detail: str = Field(default='', max_length=2000)

class GeneratedItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    concept_id: uuid.UUID
    format: Literal['mcq','short_answer','true_false','reveal_card']
    question: str = Field(min_length=5,max_length=2000)
    answer: str = Field(min_length=1,max_length=500)
    options: list[str] = Field(default_factory=list,max_length=4)
    accepted_answers: list[str] = Field(default_factory=list,max_length=12)
    rubric: str = Field(min_length=3,max_length=1500)
    explanation: str = Field(min_length=3,max_length=2000)
    hint: str = Field(min_length=3,max_length=1000)
    source_quote: str = Field(min_length=10,max_length=3000)

    @model_validator(mode='after')
    def valid_item(self):
        for field in ('question','answer','rubric','explanation','hint','source_quote'):
            value = getattr(self,field).strip()
            if not value: raise ValueError('Blank content')
            setattr(self,field,value)
        if any(not str(o).strip() or len(o)>500 for o in self.options): raise ValueError('Invalid options')
        if self.format == 'true_false':
            self.answer = normalized(self.answer)
            if self.answer not in ('true','false'): raise ValueError('Invalid true/false key')
            self.options = ['true','false']
        elif self.format == 'mcq':
            if len(self.options)!=4 or len(set(map(normalized,self.options)))!=4 or self.answer not in self.options:
                raise ValueError('MCQ key and options inconsistent')
        elif self.options: raise ValueError('Text and reveal items cannot have options')
        if any(not a.strip() or len(a)>500 for a in self.accepted_answers): raise ValueError('Invalid accepted answer')
        return self

def valid_grade(raw):
    score = raw.get('score')
    kind = raw.get('judgment')
    feedback = raw.get('feedback')
    if kind == 'unassessable':
        if not isinstance(feedback,str) or not feedback.strip(): raise ValueError('Missing clarification')
        return {'judgment':kind,'score':None,'correct':None,'feedback':feedback[:2000]}
    if isinstance(score,bool) or not isinstance(score,(float,int)) or not math.isfinite(score) or not 0<=score<=1:
        raise ValueError('Invalid grade score')
    expected = 'correct' if score>=.7 else 'partially_correct' if score>0 else 'incorrect'
    if kind!=expected or not isinstance(feedback,str) or not feedback.strip(): raise ValueError('Invalid grading verdict')
    return {'judgment':kind,'score':float(score),'correct':score>=.7,'feedback':feedback[:2000]}

def settlement(contract, results, *, abandoned=False, reason='voluntary'):
    """Deterministic requested delta; storage clamps losses at the existing balance."""
    policy = contract['xp_policy']
    graded = [r for r in results if r.get('score') is not None and r.get('kind')=='assessment']
    protected = any(r.get('independence')!='independent' or r.get('kind')=='skipped' for r in results)
    if contract['mode']=='browse_cards': return 0,'self_report_practice'
    if abandoned:
        loss = policy['loss_cap'] if graded and policy['penalties_enabled'] and not protected and reason=='voluntary' else 0
        return -loss,'voluntary_abandonment' if loss else 'ended_without_penalty'
    if not graded: return 0,'no_assessable_answers'
    avg = sum(r['score'] for r in graded)/len(graded)
    if avg<policy['poor_score_threshold'] and policy['penalties_enabled'] and not protected:
        return -policy['loss_cap'],'needs_practice_adjustment'
    scale = min(1,len(graded)/policy['item_cap'])
    return round(policy['max_xp']*avg*scale),'completed_review'
