"""Training-only equivalence and warm runtime gate; no validation selection."""
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict, frozen_count
from isl.repair_v2 import run_method as legacy
from isl.p3.repair_runtime import run_method

cases=[]
for layer in ('D1','D2-S','D2-O'):
    with zipfile.ZipFile(ROOT/f'reports/p3/P3-20261110/data/P3-train-{layer}-0000.zip') as z:
        for load in ('default','N500-h0.8'):
            d=json.loads(z.read(load+'.json'))
            for e in d['events']:
                case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],
                                        frozen_count=frozen_count(d['reference'],e['FR'])))
                cases.append((layer,load,e['scenario_index'],case))
rows=[]
keys=('plan','initial_plan','trace','forced_removed','forced_reasons','admissions_cumulative',
      'editable_indices','candidate_spans','R_window_ids','R_resource_ids','n_feas_initial',
      'validation','metrics','status','unchanged_outside_E')
for i,(layer,load,si,case) in enumerate(cases):
    start=time.perf_counter_ns()
    old=legacy(case,w=1,B=1,clock=lambda:0)
    new=run_method(case,w=1,B=1,clock=lambda:0)
    assert all(old[k]==new[k] for k in keys),(layer,load,si,[k for k in keys if old[k]!=new[k]])
    rows.append(dict(layer=layer,load=load,scenario=si,equivalent=True,wall_ns=time.perf_counter_ns()-start))
    if i%12==11: print('equivalence',i+1,'/',len(cases),flush=True)
for _,_,_,case in cases[:20]: run_method(case)
timed=[]
for layer,load,si,case in cases:
    result=run_method(case)
    timed.append(dict(layer=layer,load=load,scenario=si,status=result['status'],total_ns=result['total_ns'],
                      online_success=result['metrics']['online_success'],timings=result['timings_ns'],
                      validated=result['validated']))
report=dict(passed_equivalence=True,equivalence_scope='72 actual training cases, w1/B1, non-expiring diagnostic clock; 40 additional unit tests',
            warmup=20,equivalence=rows,timing=timed,version='0.3.3-p3-indexed-v2',validation_cases_read=0)
out=ROOT/'reports/p3/P3-20261110/runtime_acceptance.json'
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
for load in ('default','N500-h0.8'):
    rs=[r for r in timed if r['load']==load]
    print(load,'timeouts',sum(r['status']=='timeout' for r in rs),'/',len(rs),flush=True)



