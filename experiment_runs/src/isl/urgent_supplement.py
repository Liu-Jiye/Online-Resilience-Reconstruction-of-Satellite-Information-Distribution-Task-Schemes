"""Prespecified supplement generation and exact integer-start pressure labels."""
from dataclasses import asdict
from math import inf
import numpy as np
from .models import Case,case_from_dict,frozen_count
from .p2_generation import generate_base
from .p2_exact_v2 import context
from .events import generate_event


def base_attempt(ci,n,s,attempt,start,stride,prefix):
    config={'instance_seed_start':start,'instance_seed_stride':stride}
    record,data=generate_base(ci,n,s,attempt,config)
    iid=f'{prefix}-n{n}-s{s}-attempt-{attempt:04d}'
    record['instance_id']=iid
    if data:
        data['base']['id']=iid;data['metadata']['instance_id']=iid
    return record,data


def case_for(data,ratio,q,seed):
    raw={k:data[k] for k in ('base','reference')}
    raw.update(event={'id':'placeholder','kind':'reward_update','seed':0,'intensity':0,
                      'cancelled':[],'rewards':[],'urgent':None,'applicable':True},frozen_count=0)
    parsed=case_from_dict(raw)
    event=generate_event(parsed.base,parsed.reference,'urgent_insertion',ratio,q,seed)
    return Case(parsed.base,parsed.reference,event,frozen_count(parsed.reference,ratio))


def pressure_label(case,w=5,wide_w=20,full=False):
    instance=case.effective_instance();t=case.event.urgent
    narrow,wide=context(case,w,2),context(case,wide_w,2)
    frozen_ids={p.task_id for p in case.frozen}
    narrow_ids={case.reference[i].task_id for i in narrow['indices']}
    wide_ids={case.reference[i].task_id for i in wide['indices']}
    pairs=[c for c in instance.contacts if (c.sender,c.receiver)==(t.sender,t.receiver)]
    endpoints={t.sender,t.receiver}
    calendars=[b for b in instance.calendar if b.resource in endpoints]
    reservations=[p for p in case.reference if endpoints & {p.sender,p.receiver}]
    physical=calendar_ok=frozen_ok=0;small=[];large=[]
    min_small=min_large=inf
    for start in range(t.release,t.deadline-t.duration+1):
        end=start+t.duration
        if not any(c.start<=start and end<=c.end for c in pairs):continue
        physical+=1
        if any(start<b.end and b.start<end for b in calendars):continue
        calendar_ok+=1
        blocked={p.task_id for p in reservations if start<p.end and p.start<end}
        if blocked & frozen_ids:continue
        frozen_ok+=1
        if blocked<=narrow_ids:
            min_small=min(min_small,len(blocked))
            if full:small.append({'start':start,'remove_ids':sorted(blocked)})
        if blocked<=wide_ids:
            min_large=min(min_large,len(blocked))
            if full:large.append({'start':start,'remove_ids':sorted(blocked)})
    if min_small==0:category='direct_insert'
    elif min_small==1:category='one_removal'
    elif min_small<inf:category='multiple_removals'
    elif min_large<inf:category='outside_neighborhood'
    elif not physical:category='no_physical_opportunity'
    elif not calendar_ok:category='calendar_blocks_all'
    elif not frozen_ok:category='frozen_blocks_remaining'
    else:category='outside_wide_neighborhood'
    result={'category':category,'physical_start_count':physical,'calendar_start_count':calendar_ok,
            'frozen_start_count':frozen_ok,'min_removals_w5':min_small if min_small<inf else None,
            'min_removals_w20':min_large if min_large<inf else None,
            'center_index':narrow['center'],'editable_indices_w5':list(narrow['indices']),
            'editable_indices_w20':list(wide['indices'])}
    if full:result.update(feasible_starts_w5=small,feasible_starts_w20=large)
    return result


def pressure_event_seed(instance_seed):
    return int(np.random.SeedSequence([instance_seed,777]).generate_state(1,dtype=np.uint32)[0])
