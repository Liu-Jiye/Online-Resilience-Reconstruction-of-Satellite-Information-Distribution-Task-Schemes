"""Paired P5 input transformations; no method outcomes used in selection."""
from dataclasses import asdict,replace
from math import floor
import numpy as np
from ..models import Case,Contact,Event,Task,case_from_dict,frozen_count,ordered
from ..events import generate_event
from ..p1_generation import component_seeds,generate_tasks
from ..load_pilot import indexed_reference,transform_family
from ..calendar import build_calendar

def cases(d):
    return [(e,case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))) for e in d['events']]

def events_for(instance,ref,seed,ratios=(0.,.6)):
    out=[]
    for kind in ('cancellation','urgent_insertion','reward_update'):
        for fr in ratios:
            for q in (.2,.8):
                idx=(('cancellation','urgent_insertion','reward_update').index(kind)*4+(0 if fr==0 else 2)+(q==.8))
                es=int(np.random.SeedSequence([seed,93001,int(idx)]).generate_state(1,dtype=np.uint64)[0])
                e=generate_event(instance,ref,kind,fr,q,es)
                out.append(dict(FR=fr,q=q,event=asdict(e)))
    return out

def distance_contacts(records,origin,offset,distance):
    # Same propagator, visibility, scan and conservative rounding as P1, with
    # only the geometric distance threshold changed.
    from ..p1_orbits import satellite,propagate,visible,scan_runs,inward_window
    rows=sorted(records,key=lambda r:int(r['NORAD_CAT_ID']));sats=[satellite(r) for r in rows];times=np.arange(0,5401,5,dtype=float)
    positions=np.asarray([propagate(s,origin,times+offset) for s in sats]);out=[]
    for i in range(len(rows)):
        for j in range(i+1,len(rows)):
            mask=visible(positions[i],positions[j],distance=distance)
            if not np.any(mask):continue
            def refine(t):return visible(propagate(sats[i],origin,np.array([offset+t]))[0],propagate(sats[j],origin,np.array([offset+t]))[0],distance=distance)
            a,b=str(rows[i]['NORAD_CAT_ID']),str(rows[j]['NORAD_CAT_ID'])
            for k,(left,right) in enumerate(scan_runs(times,mask,refine)):
                w=inward_window(left,right)
                if right-left>=10 and w:
                    out.extend([Contact(f'{a}-{b}-{k}-f',a,b,*w),Contact(f'{a}-{b}-{k}-r',b,a,*w)])
    return tuple(out)

def transformed(base,seed,factor,value,load_config,contacts=None):
    if factor=='N':
        tasks,_=generate_tasks(base.satellites,base.contacts,np.random.Generator(np.random.PCG64(component_seeds(seed)['tasks'])),count=int(value))
        return replace(base,tasks=tasks)
    if factor=='hotspot':
        raw,details=generate_tasks(base.satellites,base.contacts,np.random.Generator(np.random.PCG64(component_seeds(seed)['tasks'])),count=100)
        tasks,_,_=transform_family(base,raw,details,seed,float(value),load_config)
        return replace(base,tasks=tasks)
    if factor=='span':return replace(base,tasks=tuple(replace(t,deadline=min(base.horizon,t.release+int(value))) for t in base.tasks))
    if factor=='rate':return replace(base,tasks=tuple(replace(t,rate_bps=int(value)*1000000) for t in base.tasks))
    if factor=='calendar':return replace(base,calendar=build_calendar(base.satellites,5400,component_seeds(seed)['calendar'],float(value))[0])
    if factor=='distance':return replace(base,contacts=contacts)
    raise ValueError(factor)

def window_case(case,seed,p=.1,shorten=.1,delete=False,target=False):
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,95101])))
    frozen=case.frozen;editable=[x for x in case.reference[case.frozen_count:] if x.task_id not in case.event.cancelled]
    contacts=list(case.base.contacts);eligible=[]
    def key(c):return (tuple(sorted((c.sender,c.receiver))),c.start,c.end)
    groups={}
    for c in contacts:groups.setdefault(key(c),[]).append(c)
    for k,cs in sorted(groups.items()):
        if any(c.sender==x.sender and c.receiver==x.receiver and c.start<=x.start and x.end<=c.end for c in cs for x in editable):eligible.append(k)
    changed={};chosen=[]
    if target:
        # First editable task by ID; trim every supporting window, provided
        # none contains a frozen transmission. Protect all frozen witnesses.
        for item in sorted(editable,key=lambda x:x.task_id):
            supports=[key(c) for c in contacts if (c.sender,c.receiver)==(item.sender,item.receiver) and c.start<=item.start and item.end<=c.end]
            if supports and not any(any(c.sender==f.sender and c.receiver==f.receiver and c.start<=f.start and f.end<=c.end for c in groups[k] for f in frozen) for k in supports):
                for k in supports:changed[k]=min(k[2],k[1]+max(1,item.end-item.start-1))
                chosen=supports;break
    else:
        selected=eligible[:1] if delete else [k for k in eligible if rng.random()<p]
        for k in selected:
            new_end=None if delete else k[1]+max(1,floor((k[2]-k[1])*(1-shorten)))
            if any(c.sender==f.sender and c.receiver==f.receiver and c.start<=f.start and f.end<=c.end and (new_end is None or new_end<f.end) for c in groups[k] for f in frozen):continue
            changed[k]=new_end;chosen.append(k)
    post=tuple(replace(c,end=changed[key(c)]) if key(c) in changed and changed[key(c)] is not None else c for c in contacts if key(c) not in changed or changed[key(c)] is not None)
    return replace(case,post_event_contacts=post),dict(changed_windows=len(changed),eligible_windows=len(eligible),keys=[list(k) for k in chosen],targeted=target)

def anomaly_case(case,index):
    assert case.reference
    frozen_n=max(1,frozen_count(case.reference,.6));victim=case.reference[0]
    if index%2==0:
        e=Event(case.event.id+':frozen-cancel','cancellation',case.event.seed,.2,cancelled=(victim.task_id,))
        return Case(case.base,case.reference,e,frozen_n),dict(type='frozen_cancel',victim=asdict(victim))
    contacts=tuple(c for c in case.base.contacts if not ((c.sender,c.receiver)==(victim.sender,victim.receiver) and c.start<=victim.start and victim.end<=c.end))
    e=Event(case.event.id+':frozen-window','reward_update',case.event.seed,.2)
    return Case(case.base,case.reference,e,frozen_n,contacts),dict(type='frozen_window',victim=asdict(victim))
