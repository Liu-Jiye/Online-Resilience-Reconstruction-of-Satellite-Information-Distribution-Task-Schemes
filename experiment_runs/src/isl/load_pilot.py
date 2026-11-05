"""Offline paired demand load pilots; no repair method or solver imports."""
from bisect import bisect_left
from collections import defaultdict
from dataclasses import replace
from math import ceil,floor
from types import SimpleNamespace
import numpy as np
from .models import Task,Item,ordered
from .p1_generation import generate_tasks
from .placement import earliest
from .validation import validate
from .events import generate_event


def rng_for(seed,tag):return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,tag])))


def demand_family(base,seed,config):
    count=500+config['opportunity_attempt_cap']
    raw,details=generate_tasks(base.satellites,base.contacts,np.random.Generator(np.random.PCG64(seed)),count=count)
    # seed here is the original task component seed; metadata separately carries
    # the base seed used for hotspots and shared transformation uniforms.
    return raw,details


def transform_family(base,raw,details,base_seed,h,config):
    hot=tuple(sorted(str(s) for s in rng_for(base_seed,config['hot_seed_tag']).choice(base.satellites,config['hot_satellites'],replace=False)))
    draws=rng_for(base_seed,config['demand_uniform_seed_tag']).random((len(raw),4))
    by_pair=defaultdict(list)
    for c in base.contacts:by_pair[(c.sender,c.receiver)].append(c)
    for pair in by_pair:by_pair[pair].sort(key=lambda c:(c.start,c.end,c.id))
    contact_pairs=sorted(p for p in by_pair if set(p)&set(hot))
    all_pairs=sorted((a,b) for a in base.satellites for b in base.satellites if a!=b and {a,b}&set(hot))
    tasks=[];sampling=[]
    for i,(t,meta) in enumerate(zip(raw,details)):
        hot_draw=draws[i,0]<h
        if hot_draw:
            contact=meta['sampling_component']=='contact_pair';pool=contact_pairs if contact else all_pairs
            if not pool:raise ValueError(f'empty_hot_pair_pool:task={i}:component={meta["sampling_component"]}')
            sender,receiver=pool[min(len(pool)-1,int(draws[i,1]*len(pool)))]
            span=meta['nominal_span_s']
            if contact:
                windows=by_pair[(sender,receiver)];c=windows[min(len(windows)-1,int(draws[i,2]*len(windows)))]
                anchor=c.start+draws[i,3]*(c.end-c.start);release=float(np.clip(anchor-span/2,0,base.horizon-span))
            else:release=float(draws[i,3]*(base.horizon-span))
            t=replace(t,sender=sender,receiver=receiver,release=ceil(release),deadline=floor(release+span))
        tasks.append(t);sampling.append({'task_id':t.id,'hot_branch':bool(hot_draw),'sampling_component':meta['sampling_component']})
    return tuple(tasks),hot,sampling


def indexed_reference(instance):
    """Same density greedy and earliest semantics, with cached input lists."""
    contacts=defaultdict(list);cal=defaultdict(list)
    for c in instance.contacts:contacts[(c.sender,c.receiver)].append(c)
    for b in instance.calendar:cal[b.resource].append(b)
    plan=()
    for task in sorted(instance.tasks,key=lambda t:t.density_key):
        proxy=SimpleNamespace(contacts=contacts[(task.sender,task.receiver)],calendar=cal[task.sender]+cal[task.receiver])
        item=earliest(proxy,task,plan)
        if item is not None:plan=ordered(plan+(item,))
    check=validate(instance,plan);assert check.feasible,check.errors
    return plan


def subtract(ranges,forbidden):
    """Closed integer start ranges, subtracting closed forbidden intervals."""
    out=[]
    for left,right in ranges:
        cursor=left
        for a,b in sorted(forbidden):
            if b<cursor:continue
            if a>right:break
            if cursor<a:out.append((cursor,min(right,a-1)))
            cursor=max(cursor,b+1)
            if cursor>right:break
        if cursor<=right:out.append((cursor,right))
    return out


class Diagnostics:
    def __init__(self,instance,reference):
        self.instance=instance;self.reference=reference
        self.contacts=defaultdict(list);self.cal=defaultdict(list);self.plan=defaultdict(list)
        for c in instance.contacts:self.contacts[(c.sender,c.receiver)].append(c)
        for b in instance.calendar:self.cal[b.resource].append(b)
        for p in reference:
            self.plan[p.sender].append(p);self.plan[p.receiver].append(p)

    def inspect(self,task,frozen_count=0):
        physical=sorted((max(task.release,c.start),min(task.deadline,c.end)-task.duration)
                        for c in self.contacts[(task.sender,task.receiver)]
                        if max(task.release,c.start)+task.duration<=min(task.deadline,c.end))
        free=subtract(physical,[(b.start-task.duration+1,b.end-1) for s in (task.sender,task.receiver) for b in self.cal[s]])
        relevant={p.task_id:p for s in (task.sender,task.receiver) for p in self.plan[s] if p.task_id!=task.id}
        frozen={p.task_id for p in self.reference[:frozen_count]}
        best=None;witness=None;editable_best=None
        for left,right in free:
            starts={left}|{p.end for p in relevant.values() if left<=p.end<=right}
            for a in sorted(starts):
                blockers=sorted(p.task_id for p in relevant.values() if a<p.end and p.start<a+task.duration)
                if best is None or len(blockers)<best:
                    best=len(blockers);witness={'start':a,'blocker_ids':blockers}
                if not frozen.intersection(blockers):
                    editable_best=len(blockers) if editable_best is None else min(editable_best,len(blockers))
        category=('no_physical' if not physical else 'calendar_blocked' if not free else 'direct' if best==0
                  else 'frozen_blocked' if editable_best is None else 'editable_blocked')
        return {'physical_feasible':bool(physical),'calendar_feasible':bool(free),'fixed_reference_min_blockers':best,
                'editable_min_blockers':editable_best,'category':category,'witness':witness}


def context_statistics(instance,reference,hot,sampling,task_labels,probe_labels):
    count=len(instance.tasks);calendar=sum(x['calendar_feasible'] for x in task_labels);physical=sum(x['physical_feasible'] for x in task_labels)
    scheduled={p.task_id for p in reference}
    blocked=[x for t,x in zip(instance.tasks,task_labels) if t.id not in scheduled and x['calendar_feasible'] and x['fixed_reference_min_blockers']>0]
    occupied=sum(p.end-p.start for p in reference)*2/(len(instance.satellites)*instance.horizon)
    hot_occupied=sum((p.end-p.start)*len({p.sender,p.receiver}&set(hot)) for p in reference)/(len(hot)*instance.horizon)
    opportunities=probe_labels['opportunity']['FR0.0'];natural=probe_labels['natural']['FR0.0']
    def summaries(labels):
        return {key:sum(x['category']==key for x in labels) for key in ('no_physical','calendar_blocked','direct','editable_blocked','frozen_blocked')}
    return {'task_count':count,'scheduled_count':len(reference),'window_fraction':physical/count,'calendar_fraction':calendar/count,
            'calendar_feasible_count':calendar,'blocked_count':len(blocked),'competition_fraction':len(blocked)/max(1,calendar),
            'unplanned_calendar_feasible_count':sum(t.id not in scheduled and x['calendar_feasible'] for t,x in zip(instance.tasks,task_labels)),
            'fixed_blockers_1':sum(x['fixed_reference_min_blockers']==1 for x in blocked),
            'fixed_blockers_2':sum(x['fixed_reference_min_blockers']==2 for x in blocked),
            'fixed_blockers_3plus':sum(x['fixed_reference_min_blockers']>=3 for x in blocked),
            'scheduled_terminal_occupancy':occupied,'hot_terminal_occupancy':hot_occupied,
            'actual_hot_endpoint_share':sum(t.sender in hot for t in instance.tasks)/count/2+sum(t.receiver in hot for t in instance.tasks)/count/2,
            'hot_branch_fraction':sum(x['hot_branch'] for x in sampling[:count])/count,
            'opportunity_probe_count':len(opportunities),'opportunity_probe_blocked_fraction':sum(x['category']=='editable_blocked' for x in opportunities)/max(1,len(opportunities)),
            'opportunity_FR0':summaries(opportunities),'natural_FR0':summaries(natural),
            'opportunity_FR0.6':summaries(probe_labels['opportunity']['FR0.6']),'natural_FR0.6':summaries(probe_labels['natural']['FR0.6'])}


def group_means(rows):
    by=defaultdict(list)
    for row in rows:by[(row['split'],row['layer'],row['N'],row['h'])].append(row)
    means={}
    numeric=['window_fraction','calendar_fraction','competition_fraction','blocked_count','opportunity_probe_blocked_fraction',
             'scheduled_count','scheduled_terminal_occupancy','hot_terminal_occupancy','actual_hot_endpoint_share','unplanned_calendar_feasible_count']
    for key,values in by.items():
        good=[r for r in values if r['status']=='valid']
        means[key]={'attempts':len(values),'valid':len(good),'all_probe_counts_complete':bool(good) and all(r['opportunity_probe_count']==20 for r in good),
                    **{n:float(np.mean([r[n] for r in good])) if good else None for n in numeric}}
    return means


def assess(means,split,N,h,level,config,medium=None):
    selection=config['selection'];rule=selection[level];reasons=[]
    for layer in config['layers']:
        row=means[(split,layer,N,h)];base=means[(split,layer,100,0.)]
        if row['valid']!=config['per_layer_split'] or row['attempts']!=config['per_layer_split']:reasons.append(layer+':generation_incomplete');continue
        if not row['all_probe_counts_complete']:reasons.append(layer+':opportunity_probes_incomplete')
        for field,threshold in [('window_fraction',selection['minimum_window_fraction']),('calendar_fraction',selection['minimum_calendar_fraction'])]:
            if row[field]<threshold:reasons.append(layer+':'+field+'_too_low')
            if base[field]-row[field]>selection['maximum_opportunity_decline_vs_default']:reasons.append(layer+':'+field+'_declined')
        lo,hi=rule['competition_fraction']
        if not lo<=row['competition_fraction']<=hi:reasons.append(layer+':competition_outside_range')
        if row['blocked_count']<rule['minimum_blocked_count']:reasons.append(layer+':blocked_count_too_low')
        if row['opportunity_probe_blocked_fraction']<rule['minimum_probe_blocked_fraction']:reasons.append(layer+':probe_competition_too_low')
        if level=='high' and medium:
            if N<medium['N']:reasons.append(layer+':N_lower_than_medium')
            if row['competition_fraction']-means[(split,layer,medium['N'],medium['h'])]['competition_fraction']<selection['minimum_high_minus_medium']:
                reasons.append(layer+':high_medium_gap_too_low')
    return reasons


def select_train(rows,config):
    means=group_means([r for r in rows if r['split']=='train']);chosen={};candidates={}
    for level in ('medium','high'):
        evaluated=[]
        for N in config['task_counts']:
            for h in config['hot_probabilities']:
                reasons=assess(means,'train',N,h,level,config,chosen.get('medium'))
                evaluated.append({'N':N,'h':h,'eligible':not reasons,'reasons':reasons})
        chosen[level]=next(({'N':x['N'],'h':x['h']} for x in evaluated if x['eligible']),None);candidates[level]=evaluated
    return {'selected_from_train':chosen,'train_candidates':candidates,'selection_used_repair_results':False}


def validate_selection(rows,training,config):
    means=group_means(rows);out={}
    for level,candidate in training['selected_from_train'].items():
        if candidate is None:out[level]={'frozen':False,'reason':'no_training_candidate'};continue
        reasons=assess(means,'validation',candidate['N'],candidate['h'],level,config,training['selected_from_train'].get('medium'))
        out[level]={'candidate':candidate,'frozen':not reasons,'validation_reasons':reasons}
    return {'default':{'N':100,'h':0.,'preserved':True},'new_layers':out,'validation_fallback_performed':False,'P3_started':False,'repair_methods_run':[]}
