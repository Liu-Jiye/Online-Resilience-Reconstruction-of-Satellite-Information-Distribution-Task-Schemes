"""Training-only runtime preflight, never parameter selection."""
import json
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict, frozen_count
from isl.repair_v2 import run_method

rows=[]
cases=[]
for index in range(2):
    p=ROOT/f'reports/p3/P3-20261110/data/P3-train-D1-{index:04d}.zip'
    with zipfile.ZipFile(p) as z:
        for load in ('default','N500-h0.8'):
            d=json.loads(z.read(load+'.json'))
            for e in d['events']:
                c=case_from_dict({'base':d['instance'],'reference':d['reference'],'event':e['event'],
                    'frozen_count':frozen_count(d['reference'],e['FR'])})
                cases.append((load,index,e,c))
for _,_,_,case in cases[:20]:
    run_method(case)
for load,index,e,c in cases:
    r=run_method(c)
    rows.append({'load':load,'base':index,'scenario':e['scenario_index'],
        'reference_n':len(c.reference),'status':r['status'],'total_ms':r['total_ns']/1e6,
        'timings_ns':r['timings_ns'],'stop_reason':r['stop_reason']})
out=ROOT/'reports/p3/P3-20261110/runtime_smoke.json'
out.write_text(json.dumps({'scope':'2 training D1 scenes only; no validation selection','warmup_calls':20,'rows':rows},indent=2)+'\n')
for load in ('default','N500-h0.8'):
    rs=[r for r in rows if r['load']==load]
    print(load,'timeouts',sum(r['status']=='timeout' for r in rs),'of',len(rs),
          'baseline_ms',[round(r['timings_ns']['input_and_baseline_ns']/1e6,2) for r in rs])
