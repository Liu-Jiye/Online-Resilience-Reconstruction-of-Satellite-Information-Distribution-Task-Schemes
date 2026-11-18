"""Rebuild P5 descriptive tables and paired exploratory intervals from replayed calls.

This stage-local analysis is not the P6 comprehensive inferential workflow.
"""
import csv,gzip,os
from collections import Counter,defaultdict
import numpy as np
import pandas as pd
from p5_common import *

PHASES=['ablations','calibration','mechanisms','simulations','upgrades','single_factor','windows','anomalies','references','transfer','continuous']
TABLES=OUT/'tables'

def write(name,rows):
    TABLES.mkdir(parents=True,exist_ok=True)
    df=rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)
    df.to_csv(TABLES/name,index=False,encoding='utf-8-sig',compression='infer')

def calls(phase):
    paths=sorted((OUT/'audit'/phase).glob('*.csv.gz'))
    assert paths,phase
    df=pd.concat([pd.read_csv(p,keep_default_na=False) for p in paths],ignore_index=True)
    for k in ['FR','q','value','w','B','search_simulations','search_iterations','search_iterations_completed']:
        if k in df:df[k]=pd.to_numeric(df[k],errors='coerce')
    for k in ('N_drop','N_add','M_all','N_forced','U_raw'):df['accepted_'+k]=df[k]*df.valid_output
    return df

def event_means(df):
    dims=['phase','base_id','root_id','layer','scenario','kind','FR','q','method','config','label','factor','value','variant','budget_ms']
    numeric=[k for k in df.select_dtypes(include='number').columns if k not in dims+['seed','spec_id']]
    g=df.groupby(dims,dropna=False,sort=False)
    result=g[numeric].mean().reset_index();result['seed_calls']=g.size().to_numpy()
    assert result.seed_calls.isin([1,5]).all()
    return result

def stats(e,raw):
    a=e[e.applicable>0];n=len(a);v=a.valid_output.sum()
    urgent=a[a.kind=='urgent_insertion']
    d=dict(event_conditions=len(e),applicable=n,na=len(e)-n,base_clusters=e.root_id.nunique(),
        success_equivalent=float(a.online_success.sum()),online_success=float(a.online_success.mean()) if n else None,
        strict_feasible=float(a.strict_feasible.mean()) if n else None,timeout_rate=float(a.timeout.mean()) if n else None,
        urgent_events=len(urgent),strict_urgent_service=float(urgent.service_success.mean()) if len(urgent) else None,
        U_exec_mean=float(a.U_exec.mean()) if n else None,valid_output_equivalent=float(v),
        conditional_U=float(a.U_exec.sum()/v) if v else None,
        raw_calls=len(raw),p50_ms=float(raw.total_ms.quantile(.5)),p95_ms=float(raw.total_ms.quantile(.95)),p99_ms=float(raw.total_ms.quantile(.99)))
    for k in ('N_drop','N_add','M_all','N_forced'):d['conditional_'+k]=float(a['accepted_'+k].sum()/v) if v else None
    return d

def grouped(e,r,dims):
    records=[]
    for key,group in e.groupby(dims,dropna=False,sort=True):
        key=key if isinstance(key,tuple) else (key,);mask=np.ones(len(r),dtype=bool)
        for name,value in zip(dims,key):mask&=r[name].isna() if pd.isna(value) else r[name].eq(value)
        records.append(dict(zip(dims,key))|stats(group,r[mask]))
    return pd.DataFrame(records)

def paired(e,left,right,label,kind='all'):
    a=e[e.label==left];b=e[e.label==right]
    if kind!='all':a=a[a.kind==kind];b=b[b.kind==kind]
    joined=a.merge(b,on=['base_id','scenario','layer'],suffixes=('_a','_b'),validate='one_to_one')
    joined=joined[(joined.applicable_a>0)&(joined.applicable_b>0)]
    if joined.empty:return None
    result=dict(comparison=label,left=left,right=right,kind=kind,paired_events=len(joined),base_clusters=joined.base_id.nunique())
    both=joined[(joined.valid_output_a==1)&(joined.valid_output_b==1)]
    result['both_valid_all_seeds_events']=len(both)
    for metric in ('U_raw','N_drop','N_add','M_all'):result['both_valid_'+metric+'_difference']=float((both[metric+'_a']-both[metric+'_b']).mean()) if len(both) else None
    rng=np.random.Generator(np.random.PCG64(20261118))
    for metric in ('online_success','U_exec'):
        joined['diff']=joined[metric+'_a']-joined[metric+'_b']
        arrays=[g.groupby('base_id')['diff'].mean().to_numpy() for _,g in joined.groupby('layer')]
        sizes=[len(g) for _,g in joined.groupby('layer')];total=sum(sizes)
        values=np.zeros(2000)
        for arr,size in zip(arrays,sizes):values+=arr[rng.integers(0,len(arr),(2000,len(arr)))].mean(axis=1)*size/total
        result[metric+'_difference']=float(joined['diff'].mean());result[metric+'_ci95_low']=float(np.quantile(values,.025));result[metric+'_ci95_high']=float(np.quantile(values,.975))
    result['interval_scope']='P5 exploratory stratified paired base-cluster bootstrap,2000 draws; conditional on fixed orbit groups,not a population-generalization CI'
    return result

def native_references():
    from ortools.sat.python import cp_model
    from ortools.sat import cp_model_pb2
    from google.protobuf import text_format
    from isl.models import Item,ordered,canonical_json
    from isl.validation import validate
    rows=[]
    for path in sorted((OUT/'references/initial_cp').glob('*.json.gz')):
        with gzip.open(path,'rt') as f:r=json.load(f)
        ident=path.name.removesuffix('.json.gz');model=cp_model.CpModel()
        text_format.Parse(r['model_text'],model.proto);assert not model.validate()
        if r['response_text']:
            native=cp_model_pb2.CpSolverResponse();text_format.Parse(r['response_text'],native)
            assert cp_model.CpSolver().status_name(native.status)==r['status']
        d=base_data(ident);from isl.p5.data import cases
        ins=cases(d)[0][1].base
        if r['plan'] is not None:
            indices={v.name:i for i,v in enumerate(model.proto.variables)}
            extracted=ordered(Item(t.id,t.sender,t.receiver,native.solution[indices['s_'+t.id]],native.solution[indices['s_'+t.id]]+t.duration) for t in ins.tasks if native.solution[indices['x_'+t.id]])
            assert canonical_json([__import__('dataclasses').asdict(p) for p in extracted])==canonical_json(r['plan'])
            assert validate(ins,extracted).feasible
            u=sum(ins.task_map[p.task_id].utility for p in extracted);assert u==r['objective']==native.objective_value
            if r['status']=='OPTIMAL':assert native.best_objective_bound==native.objective_value
        rows.append(dict(base_id=ident,status=r['status'],objective=r['objective'],best_bound=r['best_bound'],total_s=r['total_ns']/1e9,
            construction_s=r['construction_ns']/1e9,greedy_hint_utility=r['greedy_hint_utility'],reference_tasks=len(r['plan']) if r['plan'] is not None else None,
            native_model_response_checked=True,independent_plan_checked=r['plan'] is not None))
    assert len(rows)==100;write('initial_cp_references.csv',rows)
    return dict(status_counts=dict(Counter(r['status'] for r in rows)),attempts=100,independent_native_response_extraction=True,
        optimality_scope='Native solver status and bound checked; plans independently checked against ISL; no additional independent solver rerun')

def trajectories(expected_bases=100):
    from isl.models import case_from_dict,Item
    from isl.validation import validate
    rows=[]
    for path in sorted((OUT/'continuous').glob('*.json.gz')):
        with gzip.open(path,'rt') as f:records=[json.loads(line) for line in f]
        for name in LIGHT:
            group=sorted([r for r in records if r['spec']['name']==name],key=lambda x:x['step']);assert len(group)==10
            completed=set();cancellations=set();first_tasks={};delivered=0;previous_plan=None;previous_ins=None
            for record in group:
                c=case_from_dict(record['case']);now=record['decision_time'];r=record['result']
                assert now==record['step']*300
                if previous_plan is not None:
                    for p in previous_plan:
                        if p.end<=now and p.task_id not in completed:delivered+=previous_ins.task_map[p.task_id].utility;completed.add(p.task_id)
                else:
                    for p in c.reference:
                        if p.end<=now:delivered+=c.base.task_map[p.task_id].utility;completed.add(p.task_id)
                assert set(record['completed_ids'])==completed and record['delivered_so_far']==delivered
                assert all(p in c.frozen for p in c.reference if p.start<=now)
                assert not completed.intersection(t.id for t in c.base.tasks)
                assert all(t.id in {p.task_id for p in c.reference} or t.release>=now for t in c.base.tasks)
                for t in c.effective_instance().tasks:first_tasks.setdefault(t.id,t)
                cancellations.update(c.event.cancelled)
                previous_plan=tuple(Item(**p) for p in r['plan']) if r['metrics']['valid_output'] else tuple(p for p in c.reference if p.task_id not in c.event.cancelled)
                previous_ins=c.effective_instance();assert validate(previous_ins,previous_plan).feasible
            for p in previous_plan:
                if p.task_id not in completed:delivered+=previous_ins.task_map[p.task_id].utility;completed.add(p.task_id)
            window_missed=[];inherently_no_window=[]
            for tid,t in first_tasks.items():
                if tid in completed or tid in cancellations:continue
                opportunities=[min(t.deadline,x.end)-t.duration for x in previous_ins.contacts if (x.sender,x.receiver)==(t.sender,t.receiver) and max(t.release,x.start)<=min(t.deadline,x.end)-t.duration]
                (window_missed if opportunities else inherently_no_window).append(tid)
            ident=group[0]['base_id'];rc=load(path.with_suffix('.receipt.json'));reported=next(x for x in rc['summaries'] if x['method']==name)
            assert delivered==reported['delivered_utility'] and len(completed)==reported['completed_tasks']
            applicable=[x for x in group if x['result']['metrics']['applicable']]
            failures=sum(not x['result']['metrics']['online_success'] for x in applicable)
            recoveries=sum((not left['result']['metrics']['online_success']) and right['result']['metrics']['online_success'] for left,right in zip(applicable,applicable[1:]))
            corrected=dict(reported);corrected.update(recorded_calls_without_success_including_NA=reported['failures'],recorded_recoveries_including_NA=reported['failure_to_success_recoveries'],
                applicable_events=len(applicable),not_applicable_events=10-len(applicable),failures=failures,failure_to_success_recoveries=recoveries,
                online_success_rate_applicable=reported['online_success_events']/len(applicable) if applicable else None)
            assert corrected['online_success_events']+failures+corrected['not_applicable_events']==10
            rows.append(dict(**corrected,unserved_with_individually_feasible_window=len(window_missed),unserved_without_any_individual_window=len(inherently_no_window),
                window_miss_definition='through horizon5400,never executed and not cancelled,had a geometric contact/task window long enough at first appearance; not a congestion-infeasibility proof',
                denominator_note='Raw trajectory counters include N/A as no-success; published failures/recoveries recomputed over applicable events only; original counters retained separately'))
    assert len(rows)==expected_bases*4;write('continuous_trajectories.csv',rows)
    df=pd.DataFrame(rows);aggregate=df.groupby('method')[['delivered_utility','completed_tasks','applicable_events','not_applicable_events','online_success_events','failures','failure_to_success_recoveries','cumulative_active_drops','cumulative_movement','expired_unserved_tasks','unserved_with_individually_feasible_window','unserved_without_any_individual_window']].agg(['mean','sum'])
    aggregate.columns=['_'.join(c) for c in aggregate.columns];write('continuous_summary.csv',aggregate.reset_index())
    return dict(trajectories=expected_bases,methods=4,events_per_trajectory=10,all_state_progression_and_delivered_utility_recomputed=True)

def operational():
    ids=load(OUT/'subsets.json')['special_100'];p=P4/'per_event_results.csv'
    r=pd.read_csv(p);r=r[r.base_id.isin(ids)].copy();assert len(r)==19200
    for k in ('applicable','online_success','strict_feasible','service_success','valid_output'):
        if r[k].dtype==object:r[k]=r[k].map({'True':1,'False':0})
    r['root_id']=r.base_id;r['timeout']=r.total_ms>50
    for k in ('N_drop','N_add','M_all'):r['accepted_'+k]=r[k]*r.valid_output
    rows=[]
    for method,g in r.groupby('method'):
        e=g.groupby(['base_id','scenario','kind'],dropna=False).mean(numeric_only=True).reset_index();a=e[e.applicable>0];v=a.valid_output.sum()
        rows.append(dict(method=method,source='P4 historical main calls,predeclared100 timing-subset IDs,no fresh P5 calls',base_clusters=100,event_conditions=len(e),
            applicable=len(a),success_equivalent=a.online_success.sum(),online_success=a.online_success.mean(),U_exec_mean=a.U_exec.mean(),conditional_U=a.U_exec.sum()/v if v else None,
            conditional_N_drop=a.accepted_N_drop.sum()/v if v else None,conditional_N_add=a.accepted_N_add.sum()/v if v else None,conditional_M_all=a.accepted_M_all.sum()/v if v else None,
            timeout_rate=a.timeout.mean(),p95_ms=g.total_ms.quantile(.95),p99_ms=g.total_ms.quantile(.99)))
    write('historical_operational_table.csv',rows);save(TABLES/'historical_operational_provenance.json',dict(source=p.relative_to(ROOT).as_posix(),sha256=sha(p),selected_base_ids=ids,fresh_calls=0,raw_calls=19200,mechanism_inference_allowed=False))

def main():
    partial=os.environ.get('P5_SUMMARY_PARTIAL')=='1';phase_results={};paired_rows=[]
    for phase in PHASES:
        complete=OUT/phase/'COMPLETE.json'
        if not complete.exists():
            if partial:continue
            raise AssertionError('Incomplete phase '+phase)
        r=calls(phase);expected=load(complete)['calls'];assert len(r)==expected,(phase,len(r),expected)
        e=event_means(r);write(phase+'_per_call.csv.gz',r);write(phase+'_events.csv.gz',e)
        dims=['label']+(['factor','value'] if phase=='single_factor' else ['variant'] if phase in ('windows','anomalies') else [])
        table=grouped(e,r,dims);write(phase+'_summary.csv',table)
        if phase in ('ablations','mechanisms','upgrades','references','transfer'):
            write(phase+'_by_layer.csv',grouped(e,r,['label','layer']));write(phase+'_by_kind.csv',grouped(e,r,['label','kind']))
        if phase in ('ablations','single_factor','windows'):
            write(phase+'_FR_q.csv',grouped(e,r,dims+['FR','q']))
        if phase in ('ablations','windows'):
            diagnosis=[]
            for key,g in r[r.method.isin(['No-window','No-receiver'])].groupby(['label']+(['variant'] if phase=='windows' else [])):
                key=key if isinstance(key,tuple) else (key,)
                diagnosis.append(dict(label=key[0],variant=key[1] if len(key)>1 else 'natural300',calls=len(g),applicable=int(g.applicable.sum()),
                    final_rejected=int((g.validated==0).sum()),physical_illegal_plans=int((g.physical_plan_feasible==0).sum()),
                    plans_with_window_violation=int((g.physical_window_violations>0).sum()),plans_with_resource_violation=int((g.physical_resource_pairs>0).sum()),
                    plans_with_frozen_violation=int((g.physical_frozen_violations>0).sum()),online_success=int(g.online_success.sum()),
                    role='invalid-model diagnostic; all illegal outputs fail,never rank as deployable quality'))
            write(phase+'_constraint_diagnosis.csv',diagnosis)
        if phase=='simulations':
            aggregate=r.groupby('label')[['search_simulations','search_iterations','timeout','online_success','total_ms']].agg(['mean','min','max'])
            aggregate.columns=['_'.join(c) for c in aggregate.columns];write('simulation_actual_work.csv',aggregate.reset_index())
        if phase=='ablations':
            comparisons=[('Rule-PALR','Grid-w5-B2','A5 joint vs fixed'),('B-only','Grid-w5-B2','A5 B-only vs fixed'),('w-only','Grid-w5-B2','A5 w-only vs fixed'),
                ('Rule-PALR','Grid-w5-B1','A9 joint vs validation-best'),('Insert-only','Grid-w5-B2','A7 insertion vs complete'),('Random-ties','Grid-w5-B2','A8 random vs lexicographic')]
            comparisons += [(f'Rule-PALR@{b}ms',f'No-time@{b}ms','A10 time feature') for b in (5,10,20,50,100)]
            for a,b,label in comparisons:
                for kind in ('all','cancellation','urgent_insertion','reward_update'):paired_rows.append(paired(e,a,b,label,kind))
            grid=e[e.method.str.startswith('Grid-')].copy();grid=grid.sort_values(['online_success','U_exec','N_drop','N_add','M_all','total_ms','label'],ascending=[False,False,True,True,True,True,True])
            oracle=grid.drop_duplicates(['base_id','scenario']).copy();oracle['label']='Offline-25-action-oracle';oracle['method']='Offline-25-action-oracle'
            write('A9_observed_oracle_events.csv.gz',oracle);write('A9_oracle_summary.csv',[dict(label='Offline-25-action-oracle',**stats(oracle,r[r.method.str.startswith('Grid-')]),role='offline observed upper envelope of25 independent action calls; not an online50ms method,not a global optimum')])
            # Original A9 unit is a base instance: choose ONE action using its
            # complete 12-event record, then retain every event of that action.
            # The event-wise envelope above is a separate, more optimistic diagnostic.
            scores=grid.groupby(['base_id','label'],as_index=False)[['online_success','U_exec','N_drop','N_add','M_all','total_ms']].sum()
            action_order={f'Grid-w{w}-B{b}':i for i,(w,b) in enumerate((w,b) for w in (1,3,5,10,20) for b in (0,1,2,3,5))}
            scores['action_order']=scores.label.map(action_order)
            chosen=scores.sort_values(['base_id','online_success','U_exec','N_drop','N_add','M_all','total_ms','action_order'],ascending=[True,False,False,True,True,True,True,True]).drop_duplicates('base_id')
            assert len(chosen)==300
            write('A9_per_base_selected_actions.csv',chosen)
            base_oracle=grid.merge(chosen[['base_id','label']],on=['base_id','label'],validate='many_to_one').copy()
            assert len(base_oracle)==3600 and base_oracle.groupby('base_id').size().eq(12).all()
            base_oracle['selected_action']=base_oracle['label'];base_oracle['label']='Offline-per-base-grid';base_oracle['method']='Offline-per-base-grid'
            write('A9_per_base_oracle_events.csv.gz',base_oracle)
            a9_rows=[dict(label=l,**stats(e[e.label==l],r[r.label==l]),role='online fixed action') for l in ('Grid-w5-B2','Grid-w5-B1')]
            a9_rows.append(dict(label='Offline-per-base-grid',**stats(base_oracle,base_oracle),role='A9 original per-base selection from 25 actions using all12 events; retrospective, not deployable'))
            write('A9_per_base_comparison.csv',a9_rows)
            base_extended=pd.concat([e,base_oracle],ignore_index=True)
            for kind in ('all','cancellation','urgent_insertion','reward_update'):paired_rows.append(paired(base_extended,'Offline-per-base-grid','Grid-w5-B1','A9 original per-base offline grid',kind))
            extended=pd.concat([e,oracle],ignore_index=True)
            for kind in ('all','cancellation','urgent_insertion','reward_update'):paired_rows.append(paired(extended,'Offline-25-action-oracle','Grid-w5-B1','A9 offline action envelope',kind))
            ab=e[e.label.isin(['Grid-w5-B2','Grid-w5-B1','Minimal-Repair','Rule-PALR','B-only','w-only','No-window','No-receiver','Insert-only','Random-ties'])]
            write('A1_A5_A7_A8_A9_table.csv',grouped(ab,r[r.label.isin(ab.label.unique())],['label']))
        if phase=='mechanisms':
            for label in ('CP-local','PUCT-local','ALNS-local'):
                for kind in ('all','cancellation','urgent_insertion','reward_update'):paired_rows.append(paired(e,label,'PALR-local','same E and B2 mechanism',kind))
        if phase=='upgrades':
            for name in ('Upgrade-PUCT','Upgrade-ALNS'):
                for other in ('PALR-only',name.removeprefix('Upgrade-')+'-only'):
                    for kind in ('all','cancellation','urgent_insertion','reward_update'):paired_rows.append(paired(e,name,other,'shared50ms upgrade',kind))
            upgrade=[]
            for label,g in e.groupby('label'):
                base=e[e.label=='PALR-only'];join=g.merge(base,on=['base_id','scenario'],suffixes=('_u','_p'));a=join[join.applicable_u>0]
                upgrade.append(dict(label=label,applicable=len(a),trigger_equivalent=a.upgrade_triggered_u.sum(),trigger_rate=a.upgrade_triggered_u.mean(),
                    first_phase_over10_equivalent=a.first_phase_over_10ms_u.sum(),extra_success_equivalent=float((a.online_success_u-a.online_success_p).clip(lower=0).sum()),
                    lost_success_equivalent=float((a.online_success_p-a.online_success_u).clip(lower=0).sum()),net_success_equivalent=float((a.online_success_u-a.online_success_p).sum()),
                    execution_utility_difference=float((a.U_exec_u-a.U_exec_p).mean())))
            write('upgrade_diagnostics.csv',upgrade)
        if phase=='anomalies':
            diagnosis=[]
            for (label,variant),g in r.groupby(['label','variant']):diagnosis.append(dict(label=label,variant=variant,cases=len(g),frozen_conflict=int((g.status=='frozen_conflict').sum()),online_success=int(g.online_success.sum()),timeout=int(g.timeout.sum())))
            write('frozen_anomaly_detection.csv',diagnosis)
        phase_results[phase]=dict(calls=len(r),event_conditions=len(e),base_clusters=e.root_id.nunique())
        print(json.dumps(dict(summarized=phase,**phase_results[phase])),flush=True)
    write('paired_exploratory_intervals.csv',[r for r in paired_rows if r is not None])
    if not partial:
        native=native_references();continuous=trajectories();operational()
        input_rows=pd.read_csv(TABLES/'input_reference_changes.csv')
        aggregate=input_rows.groupby(['factor','value','layer'])[['task_count','reference_count','empty_reference','reference_changed','background_terminal_occupancy','planned_terminal_occupancy','planned_fraction_of_nonbackground_capacity','contact_count','contact_duration_mean']].agg(['mean','min','max'])
        aggregate.columns=['_'.join(c) for c in aggregate.columns];write('input_reference_summary.csv',aggregate.reset_index())
        save(OUT/'summary_receipt.json',dict(phases=phase_results,total_formal_calls=sum(x['calls'] for x in phase_results.values()),
            references=native,continuous=continuous,search_seed_policy='all5seeds averaged within same input/event/config; never best seed',
            statistics='P5 descriptive analysis and2000-draw exploratory conditional base-cluster intervals only; P6 not started',
            zero_baseline_policy='No normalized gain against max(1,Minimal utility) used as primary quality measure'))

if __name__=='__main__':main()
