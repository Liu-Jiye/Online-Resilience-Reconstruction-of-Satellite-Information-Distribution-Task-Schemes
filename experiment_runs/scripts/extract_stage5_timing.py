"""Exclusive P5 A5 timing decomposition from original full-call evidence."""
import gzip,time,os
from collections import defaultdict
import numpy as np
from p5_common import *

def main():
    while not (OUT/'ablations/COMPLETE.json').exists():time.sleep(10)
    selected=['Grid-w5-B2','Grid-w5-B1','Minimal-Repair','Rule-PALR','B-only','w-only'];values=defaultdict(list);totals=defaultdict(list)
    for path in sorted((OUT/'ablations').glob('*.json.gz')):
        with gzip.open(path,'rt') as f:
            for line in f:
                row=json.loads(line);spec=row['spec'];label=spec['name']
                if label not in selected or 'budget_ms' in spec:continue
                r=row['result'];components=dict(r['timings_ns']);remainder=r['total_ns']-sum(components.values());assert remainder>=0
                components['return_metrics_dispatch_ns']=remainder
                assert sum(components.values())==r['total_ns']
                totals[label].append(r['total_ns']/1e6)
                for name,ns in components.items():values[label,name].append(ns/1e6)
    records=[]
    for (label,name),v in sorted(values.items()):records.append(dict(label=label,component=name,calls=len(v),mean_ms=float(np.mean(v)),p50_ms=float(np.quantile(v,.5)),p95_ms=float(np.quantile(v,.95)),p99_ms=float(np.quantile(v,.99))))
    assert all(len(v)==3600 for v in totals.values()) and len(totals)==6
    import csv
    p=OUT/'tables/A5_timing_components.csv';p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    save(OUT/'tables/A5_timing_provenance.json',dict(source_phase='ablations',calls_per_configuration=3600,exclusive_components_sum_to_outer_total_for_every_call=True,
        return_metrics_dispatch_definition='outer total minus all recorded kernel/controller components; includes plan/result construction and metrics before final timestamp',
        all_calls_included=True,search_or_IPC_timing_inferred=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    components=sorted({k for _,k in values});fig,ax=plt.subplots(figsize=(12,5.5));bottom=np.zeros(len(selected))
    for component in components:
        height=np.array([np.mean(values[label,component]) if (label,component) in values else 0 for label in selected]);ax.bar(selected,height,bottom=bottom,label=component.removesuffix('_ns'));bottom+=height
    assert np.allclose(bottom,[np.mean(totals[label]) for label in selected])
    ax.set(ylabel='Mean full-call latency (ms)',title='P5 A5: exclusive timing decomposition, all 3600 calls/configuration');ax.tick_params(axis='x',rotation=15)
    ax.spines[['top','right']].set_visible(False);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.22),ncol=3,fontsize=9);fig.tight_layout();d=OUT/'figures';d.mkdir(exist_ok=True)
    fig.savefig(d/'A5_timing_decomposition.png',dpi=300,bbox_inches='tight');fig.savefig(d/'A5_timing_decomposition.pdf',bbox_inches='tight');plt.close(fig)
    print(json.dumps(dict(timing_decomposition_verified=True,calls=6*3600,configurations=6)),flush=True)

if __name__=='__main__':main()
