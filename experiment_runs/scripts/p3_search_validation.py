"""Training density statistics then complete paired validation of PUCT/ALNS."""
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count,canonical_json,Item
from isl.validation import validate
from isl.p3.search import run_puct,run_alns
run=ROOT/'reports/p3/P3-20261110'
cfg=json.loads((ROOT/'configs/p3_v1.json').read_text())
manifest=json.loads((run/'data/manifest.json').read_text())
stats_path=run/'search_training_statistics.json'
if not stats_path.exists():
    values=[]
    for row in manifest['instances']:
        if row['split']!='train':continue
        with zipfile.ZipFile(run/'data'/(row['id']+'.zip')) as z:
            d=json.loads(z.read('default.json'))
            values.extend(t['utility']/(1+(t['data_bits']+t['rate_bps']-1)//t['rate_bps']) for t in d['instance']['tasks'])
    assert len(values)==400000
    stats_path.write_text(canonical_json(dict(mean=float(np.mean(values)),std=float(np.std(values)),task_count=len(values),training_bases=4000,validation_used=False))+'\n')
training=json.loads(stats_path.read_text());out=run/'search';out.mkdir(exist_ok=True)
source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        sorted((ROOT/'src/isl').glob('*.py'))+sorted((ROOT/'src/isl/p3').glob('*.py'))+[Path(__file__),ROOT/'configs/p3_v1.json',stats_path]}
freeze=out/'source_freeze.json'
if freeze.exists():assert json.loads(freeze.read_text())==source
else:freeze.write_text(canonical_json(source)+'\n')
rows=[r for r in manifest['instances'] if r['split']=='validation'];warm=0;start=time.perf_counter_ns()
for bi,row in enumerate(rows):
    dest=out/(row['id']+'.json.gz');receipt=dest.with_suffix('.receipt.json')
    if receipt.exists():
        assert hashlib.sha256(dest.read_bytes()).hexdigest()==json.loads(receipt.read_text())['sha256'];continue
    records=[];jobs=[]
    with zipfile.ZipFile(run/'data'/(row['id']+'.zip')) as z:
        for label in cfg['loads']:
            d=json.loads(z.read(label+'.json'))
            for e in d['events']:
                case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                for t in cfg['PUCT']['temperatures']:jobs.append((label,e,case,['PUCT',t]))
                jobs.append((label,e,case,['ALNS',None]))
    order=np.random.Generator(np.random.PCG64(np.random.SeedSequence([row['seed'],93004]))).permutation(len(jobs))
    for j in order:
        label,e,case,setting=jobs[int(j)]
        while warm<20:
            (run_puct if warm%2==0 else run_alns)(case);warm+=1
        result=run_puct(case,temperature=setting[1],density_mean=training['mean'],density_std=training['std']) if setting[0]=='PUCT' else run_alns(case)
        if result['validated']:
            check=validate(case.effective_instance(),tuple(Item(**p) for p in result['plan']),frozen=case.frozen,cancelled=case.event.cancelled,
                original_ids={p.task_id for p in case.reference},budget=5,admissions=result['admissions_cumulative'],
                initial=tuple(Item(**p) for p in result['initial_plan']),trace=result['trace'])
            assert check.feasible,check.errors
        ins=case.effective_instance();tm=ins.task_map
        baseline=sum(tm[p.task_id].utility for p in case.reference if p.task_id not in case.event.cancelled)
        records.append(dict(base_id=row['id'],layer=row['layer'],load=label,scenario=e['scenario_index'],setting=setting,
                            reference_utility=baseline,result=result))
    temp=dest.with_suffix('.tmp')
    with gzip.open(temp,'wt',encoding='utf-8') as f:
        for r in records:f.write(canonical_json(r)+'\n')
    temp.replace(dest);receipt.write_text(canonical_json(dict(sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),calls=len(records)))+'\n')
    if bi%5==0:print(json.dumps(dict(mode='search',base_completed=bi+1,total_bases=1000,elapsed_s=(time.perf_counter_ns()-start)/1e9)),flush=True)
(out/'COMPLETE.json').write_text(canonical_json(dict(base_count=1000,full=True,mode='search'))+'\n')
