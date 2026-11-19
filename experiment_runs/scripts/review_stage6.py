"""Cross-check published calls against raw replay and summarize failure/latency evidence."""
import shutil
import numpy as np
import pandas as pd
from p6_common import *
from prepare_stage6 import p4

def quantiles(g):
    return dict(calls=len(g),mean_ms=float(g.total_ms.mean()),p50_ms=float(g.total_ms.quantile(.5)),
        p95_ms=float(g.total_ms.quantile(.95)),p99_ms=float(g.total_ms.quantile(.99)),
        timeouts=int(g.timeout.sum()),timeout_rate=float(g.timeout.mean()))

def main():
    checked={};latency=[];failures=[];statuses=[];witnesses=[]
    fields=['applicable','online_success','strict_feasible','valid_output','timeout','service_success','U_exec','U_raw','N_drop','N_add','M_all','total_ms']
    keys=['base_id','scenario','label','seed']
    for phase in ['P4']+PHASES:
        completion=load(OUT/'raw_audit'/phase/'COMPLETE.json')
        r=pd.concat([pd.read_csv(p,keep_default_na=False) for p in sorted((OUT/'raw_audit'/phase).glob('*.csv.gz'))],ignore_index=True)
        old=p4() if phase=='P4' else pd.read_csv(P5/'tables'/(phase+'_per_call.csv.gz'),keep_default_na=False)
        a=r.set_index(keys).sort_index();b=old.set_index(keys).sort_index()
        assert not a.index.duplicated().any() and a.index.equals(b.index),(phase,'index')
        for k in fields:assert np.allclose(a[k].astype(float),b[k].astype(float),rtol=1e-12,atol=1e-8),(phase,k)
        checked[phase]=dict(calls=len(a),fields=fields,passed=True,raw_replay=completion['counts'])
        r=r.merge(old[keys+['factor','value','variant','budget_ms']],on=keys,validate='one_to_one')
        for ds in [['label'],['label','layer'],['label','kind'],['label','factor','value','variant','budget_ms']]:
            for key,g in r.groupby(ds,dropna=False):
                key=key if isinstance(key,tuple) else (key,);context=dict(phase=phase,view='+'.join(ds),**dict(zip(ds,key)))
                for partition,sub in [('all_calls',g),('applicable',g[g.applicable==1]),('success',g[g.online_success==1]),('failure',g[(g.applicable==1)&(g.online_success==0)])]:
                    if len(sub):latency.append(context|dict(partition=partition,**quantiles(sub)))
                app=g[g.applicable==1];f=app[app.online_success==0]
                failures.append(context|dict(raw_calls=len(g),applicable_calls=len(app),online_success_calls=int(app.online_success.sum()),failed_calls=len(f),
                    overlapping_timeout=int(app.timeout.sum()),overlapping_not_validated=int((app.strict_feasible==0).sum()),
                    overlapping_validated_urgent_unserved=int(((app.strict_feasible==1)&(app.service_success==0)).sum()),
                    exclusive_timeout=int((f.primary_failure=='timeout').sum()),exclusive_not_validated=int((f.primary_failure=='not_validated').sum()),
                    exclusive_urgent_unserved=int((f.primary_failure=='urgent_unserved').sum())))
        statuses.extend([dict(phase=phase,label=label,status=status,calls=int(n)) for (label,status),n in r.groupby(['label','status']).size().items()])
        if phase not in ['continuous','calibration','anomalies']:
            wkeys=['base_id','scenario','input_sha256']
            known=r.groupby(wkeys).witness_service_plan.max().rename('observed_feasible_witness')
            r=r.join(known,on=wkeys)
            w=r[(r.kind=='urgent_insertion')&(r.applicable==1)&(r.observed_feasible_witness==1)]
            for label,g in w.groupby('label'):
                witnesses.append(dict(phase=phase,label=label,witness_urgent_calls=len(g),success_calls=int(g.online_success.sum()),
                    observed_service_rate=float(g.online_success.mean()),scope='Observed same actual input across methods/seeds, including late validated service; not entire physically feasible population'))
            csv(phase+'_known_feasible_witness_calls.csv.gz',w[keys+['input_sha256','online_success','total_ms','status']])
        print(json.dumps(dict(reviewed=phase,calls=len(r))),flush=True)
    csv('raw_call_latency.csv',pd.DataFrame(latency));csv('failure_review.csv',pd.DataFrame(failures));csv('solver_statuses.csv',pd.DataFrame(statuses));csv('known_feasible_service.csv',pd.DataFrame(witnesses))
    save(OUT/'published_table_crosscheck.json',dict(passed=True,phases=checked,total_calls=sum(x['calls'] for x in checked.values())))
    shutil.copyfile(P4/'timing_table.csv',OUT/'tables/P4_twenty_repeat_timing.csv')
    p2=pd.read_csv(SOURCE/'reports/p2/P2-20261105T114327Z/per_event_comparison.csv')
    assert len(p2)==200 and p2.exact_status.eq('OPTIMAL').all()
    csv('P2_exact_gap_legacy.csv',p2)
    save(OUT/'P2_legacy_summary.json',dict(events=200,optimal=200,full_lexicographic_matches=int(p2.full_lexicographic_optimum.sum()),
        mean_absolute_utility_gap=float(p2.utility_gap_to_proven_optimum.mean()),max_absolute_utility_gap=int(p2.utility_gap_to_proven_optimum.max()),
        version_scope='P2 v1 discrete local domain, earlier implementation; not a certificate of P4/P5 global online optimality'))
    save(OUT/'review_COMPLETE.json',dict(passed=True,total_calls=sum(x['calls'] for x in checked.values()),
        original_timing_calls_separately_reused=384000,latency='Raw call distributions; seeds pooled and explicitly counted; no quantiles of seed averages',
        cancelled_supplements=dict(containers_stopped_and_removed=['medium-p4-audit','medium-p4-formal','medium-preflight','medium-prepare'],
            excluded=['P4-M','P5-M','MEDIUM_P4_P5_EXECUTION_V1.md','medium*.py'],local_file_deletion='Automatic approval review rejected deletion with blocked by policy; untracked local remnants excluded from Git and evidence')))

if __name__=='__main__':main()
