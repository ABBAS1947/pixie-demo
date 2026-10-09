"""Versioned, read-only candidates; no progression or efficacy claims."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import exp, log, sqrt

MODEL_VERSION = 'bkt-pooled-v2'
RETENTION_VERSION = 'elapsed-retention-v2'

@dataclass(frozen=True)
class Point:
    judgment: str
    independence: str
    purpose: str
    created_at: datetime | None = None
    task_id: str | None = None

def eligible(p):
    return p.independence == 'independent' and p.judgment in {'correct','incorrect'} and p.purpose in {'independent','delayed'}

def timestamp(value):
    if isinstance(value, str): value = datetime.fromisoformat(value.replace('Z','+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Evidence requires an aware timestamp')
    return value.astimezone(timezone.utc)

def transition(p, correct):
    likelihood = .9*p + .2*(1-p)
    posterior = .9*p/likelihood if correct else .1*p/(1-likelihood)
    return posterior + .18*(1-posterior)

def estimate(points, now=None):
    now = timestamp(now or datetime.now(timezone.utc))
    dated = [p for p in points if p.created_at is not None]
    dated.sort(key=lambda p:(timestamp(p.created_at), str(p.task_id or '')))
    seen=set(); known=.2; count=correct=supported=unknown=0; last=None
    for p in dated:
        when=timestamp(p.created_at)
        if when>now: continue
        if p.task_id and p.task_id in seen: continue
        if p.task_id: seen.add(p.task_id)
        if not eligible(p):
            supported += p.independence=='supported'
            unknown += p.independence=='unknown'
            continue
        known=transition(known,p.judgment=='correct')
        count+=1; correct+=p.judgment=='correct'; last=when
    # Transparent provisional policy, not a fitted retention model.
    interval=max(86400,int(86400*(1+6*known))) if last else None
    due=last+timedelta(seconds=interval) if last else None
    elapsed=max(0,(now-last).total_seconds()) if last else 0
    retrieval=(.9*known+.2*(1-known))*exp(-log(2)*elapsed/interval) if last else .34
    recommendation='collect_independent_evidence' if not count else 'review' if now>=due else 'guided_practice' if known<.55 else 'transfer_check'
    return {'model_version':MODEL_VERSION,'retention_version':RETENTION_VERSION,
        'p_known':round(known,6),'answer_success_probability':round(.9*known+.2*(1-known),6),
        'uncertainty':round(1/sqrt(1+count),6),'uncertainty_kind':'evidence_sparsity_not_confidence_interval',
        'evidence_horizon':count,'supported_observations':supported,'unknown_observations':unknown,
        'undated_observations':len(points)-len(dated),'correct_independent':correct,
        'retrievability':round(retrieval,6),'next_due_at':due.isoformat() if due else None,
        'interval_seconds':interval,'overdue':bool(due and now>=due),'recommendation':recommendation,
        'used_for_progression':False,'shadow_only':True,'retention_calibrated':False,'parameters_fitted':False}

def metrics(values):
    if not values: return {'n':0,'log_loss':None,'brier':None,'auc':None,'calibration':[]}
    bins=[]
    for i in range(5):
        v=[(p,y) for p,y in values if int(min(p,.999999)*5)==i]
        if v: bins.append({'range':[i/5,(i+1)/5],'n':len(v),'predicted':sum(p for p,_ in v)/len(v),'observed':sum(y for _,y in v)/len(v)})
    positive_count=sum(y for _,y in values); negative_count=len(values)-positive_count
    ranked=sorted(values); rank_sum=0; index=0
    while index<len(ranked):
        end=index+1
        while end<len(ranked) and ranked[end][0]==ranked[index][0]: end+=1
        rank_sum+=((index+1+end)/2)*sum(y for _,y in ranked[index:end]); index=end
    auc=(rank_sum-positive_count*(positive_count+1)/2)/(positive_count*negative_count) if positive_count and negative_count else None
    return {'n':len(values),'log_loss':sum(-log(max(1e-9,min(1-1e-9,p if y else 1-p))) for p,y in values)/len(values),
        'brier':sum((p-y)**2 for p,y in values)/len(values),'auc':auc,'calibration':bins}

def evaluate(events, holdout_fraction=.2):
    if not 0<holdout_fraction<1: raise ValueError('holdout_fraction must be between zero and one')
    groups={}; rejected=duplicates=family_repeats=0; family_coverage=True
    for e in events:
        if e.get('independence')!='independent' or e.get('purpose') not in {'independent','delayed'} or e.get('judgment') not in {'correct','incorrect'}: continue
        try: when=timestamp(e.get('created_at'))
        except (ValueError,TypeError): rejected+=1; continue
        if not e.get('learner_id') or not e.get('skill_code') or not e.get('task_id'): rejected+=1; continue
        key=(e['learner_id'],e['skill_code'],e.get('skill_version',1))
        groups.setdefault(key,[]).append((when,e))
    values={name:[] for name in ('bkt','performance_factor','baseline')}; subgroups={}
    for rows in groups.values():
        rows.sort(key=lambda row:(row[0],str(row[1]['task_id'])))
        seen=set(); unique=[]
        for row in rows:
            if row[1]['task_id'] in seen: duplicates+=1; continue
            seen.add(row[1]['task_id']); unique.append(row)
        cut=max(1,int(len(unique)*(1-holdout_fraction))); known=.2; baseline=.5; successes=failures=0; prior_families=set()
        for i,(_,e) in enumerate(unique):
            y=int(e['judgment']=='correct')
            logit=max(-35,min(35,-.66+.7*successes-.9*failures))
            probs={'bkt':.9*known+.2*(1-known),'performance_factor':1/(1+exp(-logit)),'baseline':baseline}
            family=e.get('item_family') or e.get('content_hash')
            if not family: family_coverage=False
            if i>=cut and family and family in prior_families: family_repeats+=1
            elif i>=cut:
                for name,p in probs.items(): values[name].append((p,y))
                for dimension,label in e.get('subgroups',{}).items():
                    bucket=subgroups.setdefault(f'{dimension}:{label}',{name:[] for name in values})
                    for name,p in probs.items(): bucket[name].append((p,y))
            baseline+=max(.1,.3-.02*(successes+failures))*(y-baseline)
            known=transition(known,bool(y)); successes+=y; failures+=1-y
            if family: prior_families.add(family)
    return {'eligible':False,'gate':'shadow_only','reason':'Requires real-data provenance, subgroup coverage and reviewed rollout approval',
        'n':len(values['bkt']),'rejected':rejected,'duplicates_removed':duplicates,'repeated_families_excluded':family_repeats,'item_family_coverage_complete':family_coverage,
        'models':{name:metrics(v) for name,v in values.items()},
        'subgroups':{label:{name:metrics(v) for name,v in bucket.items()} for label,bucket in subgroups.items()},
        'evaluation_mode':'chronological_prequential_future_holdout','model_version':MODEL_VERSION,'baseline_version':'review-shrinking-k-v1'}
