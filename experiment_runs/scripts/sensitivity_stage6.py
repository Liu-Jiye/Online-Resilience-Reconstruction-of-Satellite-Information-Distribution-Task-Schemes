"""Paired changed-condition versus original-input sensitivity; no timing pooling."""
import numpy as np
import pandas as pd
from p6_common import *
from p6_bootstrap import ratio,interval
from analyze_stage6 import bootstrap,METRICS

def main():
    original=pd.read_csv(OUT/'tables/P4_events.csv.gz',keep_default_na=False)
    rows=[];replicates={}
    for phase in ['references','windows']:
        changed=pd.read_csv(OUT/'tables'/(phase+'_events.csv.gz'),keep_default_na=False)
        for (label,variant),g in changed.groupby(['label','variant'],dropna=False):
            if label not in original.label.unique():continue
            keys=['root_id','layer','kind','FR','q']
            j=g.merge(original[original.label==label],on=keys,suffixes=('_changed','_original'),validate='one_to_one')
            assert len(j)==len(g)
            b=bootstrap(j.root_id.unique())
            for metric,(num,den) in METRICS.items():
                if metric not in ['online_success','U_exec','conditional_U','conditional_N_drop','conditional_M_all']:continue
                fields=[]
                for suffix in ['changed','original']:
                    fields += [num+'_'+suffix,den+'_'+suffix]
                a=j.groupby('root_id')[fields].sum().reindex(b.ids,fill_value=0)
                arr=a.to_numpy();tot=arr.sum(0);pt=float(ratio(tot[0],tot[1])-ratio(tot[2],tot[3]))
                for mode in ['hierarchical','base_only']:
                    v=b.apply(arr,mode);diff=ratio(v[:,0],v[:,1])-ratio(v[:,2],v[:,3])
                    key=f'{phase}::{label}::{variant}::{metric}::{mode}';replicates[key]=diff.astype(np.float32)
                    rows.append(dict(phase=phase,label=label,variant=variant,metric=metric,bootstrap=mode,estimate=pt,
                        paired_event_conditions=len(j),base_clusters=len(b.ids),resampling_plan=b.key,**interval(diff),
                        interpretation='Changed condition minus original; paired roots/events, original vs P5 measurements from separate time sessions'))
    csv('paired_condition_sensitivity.csv',pd.DataFrame(rows));np.savez_compressed(OUT/'replicates/paired_condition_sensitivity.npz',**replicates)
    save(OUT/'sensitivity_COMPLETE.json',dict(passed=True,repetitions=REPS,comparisons=len(rows),scope='CP reference and paired window conditions versus original P4 same-root input; latency not pooled'))

if __name__=='__main__':main()
