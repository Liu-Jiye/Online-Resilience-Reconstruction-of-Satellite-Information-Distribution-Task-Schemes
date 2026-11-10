"""Derived input distribution and frozen snapshot provenance; no method metrics."""
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];run=ROOT/'reports/p3/P3-20261110'
manifest=json.loads((run/'data/manifest.json').read_text());cells=defaultdict(list);rows=[];events=Counter()
for row in manifest['instances']:
    with zipfile.ZipFile(run/'data'/(row['id']+'.zip')) as z:
        for name in ('default','N500-h0.8'):
            d=json.loads(z.read(name+'.json'));ins=d['instance'];ref=d['reference'];N=len(ins['tasks'])
            busy=sum(b['end']-b['start'] for b in ins['calendar'])
            scheduled=2*sum(p['end']-p['start'] for p in ref);capacity=32*5400
            r=dict(base_id=row['id'],split=row['split'],layer=row['layer'],load=name,seed=row['seed'],
                   tasks=N,reference_count=len(ref),scheduled_fraction=len(ref)/N,
                   background_occupancy=busy/capacity,scheduled_occupancy=scheduled/capacity,
                   combined_occupancy=(busy+scheduled)/capacity,contacts=len(ins['contacts']))
            rows.append(r);cells[(row['split'],row['layer'],name)].append(r)
            for e in d['events']:events[(row['split'],name,e['scenario_index'])]+=1
report=[]
for (split,layer,load),rs in cells.items():
    record=dict(split=split,layer=layer,load=load,bases=len(rs))
    for key in ('reference_count','scheduled_fraction','background_occupancy','scheduled_occupancy','combined_occupancy','contacts'):
        vs=[r[key] for r in rs];record[key]=dict(mean=float(np.mean(vs)),min=float(min(vs)),p50=float(np.percentile(vs,50)),p95=float(np.percentile(vs,95)),max=float(max(vs)))
    report.append(record)
with (run/'input_distributions.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
registry=ROOT/'reports/p1/P1-20261105T110427Z/source_and_license_registry.json'
raw={}
for name in ('starlink','oneweb'):
    p=ROOT/f'data/raw/p1_snapshot_20261105/{name}.json'
    raw[name]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),downloaded_again=False,uploaded_raw=False)
report=dict(base_scenes=5000,paired_variants=10000,test_scenes=0,cells=report,
            raw_snapshot=raw,license_registry=dict(path=str(registry.relative_to(ROOT)),sha256=hashlib.sha256(registry.read_bytes()).hexdigest()),
            event_counts=[dict(split=s,load=l,scenario=i,n=n) for (s,l,i),n in events.items()],
            caveat='paired loads and multiple events are clustered by5000base scenes, not independent replications')
(run/'input_summary.json').write_text(json.dumps(report,indent=2)+'\n')
print('P3 input distribution report complete',flush=True)
