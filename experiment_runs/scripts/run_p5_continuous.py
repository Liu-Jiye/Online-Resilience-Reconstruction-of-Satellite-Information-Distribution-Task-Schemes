"""100 independent paired trajectories,10 successive events each, method-owned states."""
import gzip,time
from dataclasses import replace,asdict
from p5_runner import *
from isl.models import Case,Event,Task,Instance,ordered
from isl.events import generate_event

def update_state(ins,event):
    from isl.models import apply_event
    updated=apply_event(ins,event)
    return replace(updated,tasks=tuple(t for t in updated.tasks if t.id not in event.cancelled))

def main():
    rule,stats=config();sub=load(OUT/'subsets.json')
    mode=os.environ.get('P5_CONTINUOUS_PREFLIGHT','')
    preflight=bool(mode)
    phase=('semantic_continuous' if mode=='semantic' else 'preflight_continuous') if preflight else 'continuous'
    if preflight:
        training=load(P3/'data/manifest.json')['instances'][0]
        sub=dict(continuous_100=[training['id']],layers={training['id']:training['layer']})
    jobs=[dict(name='Minimal-Repair'),dict(name='Fixed-PALR',w=5,B=2),dict(name='Validation-Best-Fixed',w=5,B=1),dict(name='Rule-PALR')]
    extra=dict(specs=jobs,trajectories=len(sub['continuous_100']),events=10,interval_s=300,extra_future_FR=.6)
    if mode=='semantic':
        # CPU2 offline semantic smoke check is separate from timed CPU0 batches.
        save(OUT/phase/'source_freeze.json',dict(sources=source_hashes(),extra=extra,scope='training semantic preflight only; no performance inference'))
        freeze=sha(OUT/phase/'source_freeze.json')
    else:freeze=frozen_phase(phase,extra)
    session=warm(jobs,rule,stats,phase);summaries=[]
    for bi,ident in enumerate(sub['continuous_100']):
        dest=OUT/phase/(ident+'.json.gz');receipt=dest.with_suffix('.receipt.json')
        if receipt.exists():
            rc=load(receipt);assert sha(dest)==rc['sha256'] and rc['freeze']==freeze;summaries+=rc['summaries'];continue
        original=cases(base_data(ident,P3 if preflight else P4))[0][1]
        states={j['name']:dict(instance=original.base,plan=original.reference,completed=set(),expired=set(),delivered=0,failures=0,successes=0,movement=0,drops=0,missed=0,recoveries=0,last_failure=False) for j in jobs}
        records=[]
        for step in range(10):
            now=step*300;seed=int.from_bytes(__import__('hashlib').sha256((ident+str(step)).encode()).digest()[:8],'little')
            rng=np.random.Generator(np.random.PCG64(seed));kind=('cancellation','urgent_insertion','reward_update')[step%3];q=(.2,.8)[step%2]
            # Shared exogenous random seed and kind; own reference determines
            # legal cancellations/frozen commitments, as required for trajectories.
            for ji in rng.permutation(len(jobs)):
                spec=jobs[int(ji)];state=states[spec['name']];ins=state['instance'];plan=state['plan'];tm=ins.task_map
                for p in plan:
                    if p.end<=now and p.task_id not in state['completed']:
                        state['delivered']+=tm[p.task_id].utility;state['completed'].add(p.task_id)
                active=[p for p in plan if p.end>now];past=[p for p in plan if p.end<=now]
                # Expired unexecuted jobs cannot be resurrected in later rounds.
                eligible=tuple(t for t in ins.tasks if t.id not in state['completed'] and (t.deadline>now or any(p.task_id==t.id for p in active)))
                state['expired'].update(t.id for t in ins.tasks if t.id not in state['completed'] and t.deadline<=now and not any(p.task_id==t.id for p in active))
                ins=replace(ins,tasks=eligible)
                adjusted=tuple(replace(t,release=max(t.release,now)) if not any(p.task_id==t.id and p.start<now for p in active) and t.deadline>now else t for t in ins.tasks)
                ins=replace(ins,tasks=adjusted)
                active=ordered(active);started=sum(p.start<now for p in active);future=len(active)-started;frozen_n=started+int(np.floor(.6*future))
                reference=active
                # Reference items starting in future remain legal after release clipping.
                assert validate(ins,reference).feasible
                event=generate_event(ins,reference,kind,0.,q,seed)
                if kind=='cancellation':
                    editable=sorted(p.task_id for p in reference[frozen_n:]);k=min(len(editable),max(1,int(np.ceil(q*len(editable)))))
                    chosen=tuple(sorted(str(x) for x in np.random.Generator(np.random.PCG64(seed)).choice(editable,k,replace=False))) if editable else ()
                    event=replace(event,cancelled=chosen,applicable=bool(editable))
                elif kind=='reward_update':
                    frozen_ids={p.task_id for p in reference[:frozen_n]};event=replace(event,rewards=tuple((t,u) for t,u in event.rewards if t not in frozen_ids))
                else:event=replace(event,urgent=replace(event.urgent,id=f'urgent:{ident}:step{step}',release=now,deadline=min(ins.horizon,now+(600 if q==.2 else 120))))
                c=Case(ins,reference,event,frozen_n);r=execute(c,spec,rule,stats);audit(c,r)
                good=r['metrics']['valid_output'];success=r['metrics']['online_success']
                if success:state['successes']+=1;state['recoveries']+=int(state['last_failure'])
                else:state['failures']+=1
                state['last_failure']=not success;state['movement']+=r['metrics']['M_all'] if good else 0;state['drops']+=r['metrics']['N_drop'] if good else 0
                if good:newplan=tuple(Item(**p) for p in r['plan'])
                else:newplan=ordered(p for p in reference if p.task_id not in event.cancelled)
                newins=update_state(ins,event)
                assert validate(newins,newplan).feasible
                state['plan']=newplan;state['instance']=newins
                records.append(dict(base_id=ident,layer=sub['layers'][ident],step=step,decision_time=now,spec=spec,
                    case=case_to_dict(c),result=r,fallback_used=not good,delivered_so_far=state['delivered'],completed_ids=sorted(state['completed']),session=session))
        summary=[]
        for name,state in states.items():
            tm=state['instance'].task_map
            for p in state['plan']:
                if p.task_id not in state['completed']:state['delivered']+=tm[p.task_id].utility;state['completed'].add(p.task_id)
            state['missed']=sum(t.id not in state['completed'] for t in state['instance'].tasks)
            summary.append(dict(base_id=ident,layer=sub['layers'][ident],method=name,delivered_utility=state['delivered'],completed_tasks=len(state['completed']),
                online_success_events=state['successes'],failures=state['failures'],failure_to_success_recoveries=state['recoveries'],
                cumulative_active_drops=state['drops'],cumulative_movement=state['movement'],unserved_tasks_at_end=state['missed'],expired_unserved_tasks=len(state['expired']),
                scope='executions through horizon5400; each completed task utility counted once'))
        temp=dest.with_suffix('.tmp')
        with gzip.open(temp,'wt') as f:
            for r in records:f.write(canonical_json(r)+'\n')
        temp.replace(dest);save(receipt,dict(sha256=sha(dest),freeze=freeze,calls=len(records),summaries=summary));summaries+=summary
        if bi%5==0:print(json.dumps(dict(phase=phase,trajectories=bi+1,total=len(sub['continuous_100']))),flush=True)
    save(OUT/phase/'trajectory_summary.json',dict(trajectories=len(sub['continuous_100']),events_per_trajectory=10,methods=4,rows=summaries))
    save(OUT/phase/'COMPLETE.json',dict(trajectories=len(sub['continuous_100']),calls=len(sub['continuous_100'])*40,freeze=freeze))

if __name__=='__main__':main()
