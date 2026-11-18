"""Independent phase handoff, local-domain, and A9 selection acceptance.

Runs offline after formal evidence is sealed. Does not call a repair/search method.
"""
import gzip
from collections import Counter
from dataclasses import replace
from p5_common import *
from isl.models import Item,case_from_dict
from isl.p5.data import cases
from isl.validation import validate
from isl.p3r.indexed import IndexedInstance
from isl.p3r.repair_runtime import center_and_region


def check_continuous_states(counts,phase='continuous',source=P4,expected_bases=100):
    """Reconstruct method-owned input states without the experiment runner."""
    from isl.models import ordered
    for path in sorted((OUT/phase).glob('*.json.gz')):
        ident=path.name.removesuffix('.json.gz')
        original=cases(base_data(ident,source))[0][1]
        with gzip.open(path,'rt') as f:records=[json.loads(line) for line in f]
        for name in LIGHT:
            group=sorted((r for r in records if r['spec']['name']==name),key=lambda r:r['step'])
            assert len(group)==10
            previous_tasks=original.base.task_map
            previous_plan=original.reference
            completed=set();expired=set();cancelled=set();delivered=0
            for step,record in enumerate(group):
                c=case_from_dict(record['case']);now=step*300
                assert record['step']==step and record['decision_time']==now
                for p in previous_plan:
                    if p.end<=now and p.task_id not in completed:
                        completed.add(p.task_id);delivered+=previous_tasks[p.task_id].utility
                active=ordered(p for p in previous_plan if p.end>now)
                assert c.reference==active
                active_ids={p.task_id for p in active}
                started_ids={p.task_id for p in active if p.start<=now}
                expected={}
                for tid,t in previous_tasks.items():
                    if tid in completed:continue
                    if t.deadline<=now and tid not in active_ids:
                        expired.add(tid);continue
                    expected[tid]=replace(t,release=max(t.release,now)) if tid not in started_ids and t.deadline>now else t
                assert c.base.task_map==expected
                assert not (completed|expired|cancelled).intersection(expected)
                assert c.frozen_count==len(started_ids)+int(.6*(len(active)-len(started_ids)))
                assert record['completed_ids']==sorted(completed) and record['delivered_so_far']==delivered
                assert not set(c.event.cancelled).intersection(p.task_id for p in c.frozen)
                assert not set(t for t,_ in c.event.rewards).intersection(p.task_id for p in c.frozen)
                r=record['result'];good=r['metrics']['valid_output']
                assert record['fallback_used']==(not good)
                previous_plan=plans(r) if good else ordered(p for p in active if p.task_id not in c.event.cancelled)
                cancelled.update(c.event.cancelled)
                previous_tasks={t.id:t for t in c.effective_instance().tasks if t.id not in c.event.cancelled}
                assert not cancelled.intersection(previous_tasks)
                counts['continuous_input_state_calls_checked']+=1
            for p in previous_plan:
                if p.task_id not in completed:
                    completed.add(p.task_id);delivered+=previous_tasks[p.task_id].utility
            receipt=load(path.with_suffix('.receipt.json'))
            summary=next(r for r in receipt['summaries'] if r['method']==name)
            assert summary['expired_unserved_tasks']==len(expired)
            assert summary['completed_tasks']==len(completed) and summary['delivered_utility']==delivered
            counts['continuous_method_trajectories_checked']+=1
    assert counts['continuous_input_state_calls_checked']==expected_bases*40
    assert counts['continuous_method_trajectories_checked']==expected_bases*4


def plans(result,key='plan'):
    return tuple(Item(**p) for p in result[key])


def check_phase(c,r):
    if not r['validated']:return
    check=validate(c.effective_instance(),plans(r),frozen=c.frozen,cancelled=c.event.cancelled,
        original_ids={p.task_id for p in c.reference},budget=r['B'],admissions=r['admissions_cumulative'],
        initial=plans(r,'initial_plan'),trace=r['trace'],unchanged=plans(r,'unchanged_outside_E'))
    assert check.feasible,check.errors


def check_completed_searches():
    counts=Counter();early_returns=[];threshold=load(OUT/'upgrade_threshold.json')['threshold']
    for path in sorted((OUT/'upgrades').glob('*.json.gz')):
        ident=path.name.removesuffix('.json.gz');cs=cases(base_data(ident))
        with gzip.open(path,'rt') as f:
            for line in f:
                row=json.loads(line)
                if not row['spec']['name'].startswith('Upgrade-'):continue
                r=row['result'];c=cs[row['scenario']][1];first=r['phases'][0]
                tm=c.effective_instance().task_map
                ref=sum(tm[p.task_id].utility for p in c.reference if p.task_id not in c.event.cancelled)
                service=first['validated'] and first['metrics']['service_success']
                ratio=first['metrics']['U_raw']/max(1,ref) if first['validated'] else 0.
                trigger=(bool(c.event.urgent) and not service) or ratio<threshold
                assert trigger==r['upgrade_triggered']
                assert r['budget_ms']==50 and r['B']==5
                assert r['first_phase_ns']==first['total_ns'] and r['first_phase_ns']<=r['total_ns']
                assert r['first_phase_over_10ms']==(r['first_phase_ns']>10_000_000)
                assert r['search_phase_started']==(len(r['phases'])==2)
                assert any(r['plan']==phase['plan'] for phase in r['phases'])
                for phase in r['phases']:check_phase(c,phase);counts['upgrade_phase_plans_checked']+=1
                if len(r['phases'])==2:
                    second=r['phases'][1]
                    assert trigger and second['budget_ms']<=max(0.,50-r['first_phase_ns']/1e6)+1e-6
                    assert sum(x['total_ns'] for x in r['phases'])<=r['total_ns']
                    if first['validated']:
                        assert second['initial_plan']==first['initial_plan']
                        assert second['trace'][:len(first['trace'])]==first['trace']
                        assert second['admissions_cumulative']>=first['admissions_cumulative']
                        counts['warm_incumbent_handoffs_checked']+=1
                counts['upgrade_calls_checked']+=1
    assert counts['upgrade_calls_checked']==12000
    for path in sorted((OUT/'mechanisms').glob('*.json.gz')):
        ident=path.name.removesuffix('.json.gz');cs=cases(base_data(ident));domains={}
        for i,(_,c) in enumerate(cs):
            _,indices,spans=center_and_region(c,IndexedInstance(c.effective_instance()),5)
            editable={c.reference[j].task_id for j in indices}
            domains[i]=(tuple(p for p in c.reference if p.task_id not in c.event.cancelled and p.task_id not in editable),spans)
        with gzip.open(path,'rt') as f:
            for line in f:
                row=json.loads(line);r=row['result'];c=cs[row['scenario']][1]
                assert r['B']==2
                if r['validated']:
                    expected,spans=domains[row['scenario']]
                    recorded=set(plans(r,'unchanged_outside_E'))
                    if recorded!=set(expected):
                        # PALR can reach its cooperative reserve after verifying
                        # the unchanged baseline, before E metadata is populated.
                        # Certify this narrow path, and always check the actual
                        # E-outside plan below, rather than trusting the field.
                        assert row['spec']['name']=='PALR-local' and not recorded
                        assert r['stop_reason']=='cooperative_deadline' and not r['trace']
                        assert r['plan']==r['initial_plan']
                        assert r['timings_ns']['filter_ns']==0 and r['timings_ns']['repair_ns']==0
                        assert set(plans(r))=={p for p in c.reference if p.task_id not in c.event.cancelled}
                        early_returns.append(dict(base_id=ident,scenario=row['scenario'],total_ns=r['total_ns'],expected_outside_count=len(expected)))
                        counts['local_certified_early_baseline_returns']+=1
                    assert set(expected)<=set(plans(r))
                    old={p.task_id for p in c.reference};tm=c.effective_instance().task_map
                    for p in plans(r):
                        if p.task_id not in old:
                            t=tm[p.task_id]
                            assert (c.event.urgent and t.id==c.event.urgent.id) or any(t.release<b and a<t.deadline for a,b in spans)
                counts['local_domain_calls_checked']+=1
    assert counts['local_domain_calls_checked']==14400
    save(OUT/'local_domain_early_returns.json',dict(cases=early_returns,
        explanation='Cooperative return after baseline validation and before E metadata population; no edits, original surviving plan retained, independently reconstructed E-outside commitments all preserved. No method or raw output changed.'))
    return counts


def main():
    assert (OUT/'pipeline/COMPLETE.json').exists()
    counts=check_completed_searches()
    import pandas as pd
    depth=[]
    for path in sorted((OUT/'simulations').glob('*.json.gz')):
        with gzip.open(path,'rt') as f:
            for line in f:
                row=json.loads(line);r=row['result'];stats=r['search_stats']
                depth.append(dict(base_id=row['base_id'],scenario=row['scenario'],seed=row['spec']['seed'],
                    requested_simulations=row['spec']['simulations'],completed_simulations=stats['simulations'],
                    max_depth=stats['max_depth'],expanded_nodes=stats['expanded_nodes'],total_ms=r['total_ns']/1e6,
                    stop_reason=r['stop_reason'],online_success=r['metrics']['online_success']))
    assert len(depth)==18000
    d=pd.DataFrame(depth);d.to_csv(OUT/'tables/simulation_depth_per_call.csv.gz',index=False,compression='gzip')
    ds=d.groupby('requested_simulations')[['completed_simulations','max_depth','expanded_nodes']].agg(['mean','min','max'])
    ds.columns=['_'.join(c) for c in ds.columns]
    ds.reset_index().to_csv(OUT/'tables/simulation_depth_summary.csv',index=False)
    counts['simulation_depth_calls_exported']=len(depth)
    e=pd.read_csv(OUT/'tables/ablations_events.csv.gz',keep_default_na=False)
    selected=pd.read_csv(OUT/'tables/A9_per_base_selected_actions.csv')
    oracle=pd.read_csv(OUT/'tables/A9_per_base_oracle_events.csv.gz')
    for _,row in selected.iterrows():
        g=e[(e.base_id==row.base_id)&e.method.str.startswith('Grid-')]
        scores=[]
        for i,(w,b) in enumerate((w,b) for w in (1,3,5,10,20) for b in (0,1,2,3,5)):
            label=f'Grid-w{w}-B{b}';a=g[g.label==label];assert len(a)==12
            scores.append(((-a.online_success.sum(),-a.U_exec.sum(),a.N_drop.sum(),a.N_add.sum(),a.M_all.sum(),a.total_ms.sum(),i),label))
        assert row.label==min(scores)[1]
        chosen=oracle[oracle.base_id==row.base_id]
        assert len(chosen)==12 and set(chosen.selected_action)=={row.label}
        original=g[g.label==row.label].set_index('scenario').sort_index()
        chosen=chosen.set_index('scenario').sort_index()
        for col in ('online_success','U_exec','N_drop','N_add','M_all','total_ms'):
            assert __import__('numpy').allclose(chosen[col],original[col],rtol=0,atol=1e-12)
        counts['per_base_A9_selections_checked']+=1
    assert counts['per_base_A9_selections_checked']==300
    check_continuous_states(counts)
    save(OUT/'acceptance_details.json',dict(passed=True,counts=counts,
        scope='Independent original checker for both upgrade phases, cumulative handoff, shared deadline accounting, local E/B2 and candidate eligibility, original per-base A9 selection, method-owned continuous references/tasks/rewards/cancellations/expiry/release/freeze/delivery; no performance rerun'))
    print(json.dumps(dict(passed=True,counts=counts)),flush=True)


if __name__=='__main__':main()
