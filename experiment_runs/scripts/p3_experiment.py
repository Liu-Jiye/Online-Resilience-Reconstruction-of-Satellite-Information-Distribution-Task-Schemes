"""Resumable sequential single-core P3 labels and validation; per-call evidence."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count,canonical_json,Item
from isl.validation import validate
from isl.p3.repair_runtime import run_method
from isl.p3.control import features,controlled


def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('mode',choices=['labels','grid','rules','et']); ap.add_argument('--limit',type=int,default=0)
    args=ap.parse_args(); cfg=load(ROOT/'configs/p3_v1.json'); run=ROOT/'reports/p3/P3-20261110'
    manifest=load(run/'data/manifest.json'); split='train' if args.mode=='labels' else 'validation'
    rows=[r for r in manifest['instances'] if r['split']==split]
    if args.limit: rows=rows[:args.limit]
    out=run/args.mode; out.mkdir(exist_ok=True)
    actions=[(w,b) for w in cfg['w'] for b in cfg['B'] if args.mode!='labels' or b>0]
    model=None
    if args.mode=='et':
        from isl.p3.model_io import load_model
        model=load_model(run/'models')
        frozen=load(run/'selection_fixed_rule.json')
    # Whole measured runtime source must be frozen before starting labels/grid.
    dependencies=sorted((ROOT/'src/isl').glob('*.py'))+[ROOT/'src/isl/p3'/n for n in
        ('__init__.py','indexed.py','repair_runtime.py','validation_indexed.py','control.py','model_io.py')]
    source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in dependencies+[Path(__file__),ROOT/'configs/p3_v1.json']}
    freeze=out/'source_freeze.json'
    if freeze.exists(): assert load(freeze)==source,'source changed; cannot mix versions'
    else: freeze.write_text(canonical_json(source)+'\n',encoding='utf-8')
    warm=0; calls=0; begun=time.perf_counter_ns()
    for bi,row in enumerate(rows):
        dest=out/(row['id']+'.json.gz'); receipt=dest.with_suffix('.receipt.json')
        if receipt.exists():
            assert hashlib.sha256(dest.read_bytes()).hexdigest()==load(receipt)['sha256']; continue
        records=[];state_cache={}
        with zipfile.ZipFile(run/'data'/(row['id']+'.zip')) as z:
            loads=['default'] if args.mode=='labels' else cfg['loads']
            jobs=[]
            for label in loads:
                d=json.loads(z.read(label+'.json'))
                events=[d['events'][row['global_index']%12]] if args.mode=='labels' else d['events']
                for e in events:
                    case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    if args.mode in ('labels','grid'): settings=[dict(w=w,B=b) for w,b in actions]
                    elif args.mode=='rules': settings=[dict(rule=r) for r in cfg['rule_candidates']]
                    else: settings=[dict(rule=next(r for r in cfg['rule_candidates'] if r['name']==frozen[label]['rule']['name']),
                                         model=model,threshold=p,time_ratio=t) for p in cfg['ET']['probabilities'] for t in cfg['ET']['time_ratios']]
                    jobs.extend((label,e,case,setting) for setting in settings)
            order=np.random.Generator(np.random.PCG64(np.random.SeedSequence([row['seed'],cfg['method_order_tag']]))).permutation(len(jobs))
            for j in order:
                label,e,case,setting=jobs[int(j)]
                while warm<20:
                    run_method(case); warm+=1
                feature_vector=None; feature_ns=None
                if args.mode in ('labels','grid'):
                    state_key=(label,e['scenario_index'])
                    if state_key not in state_cache:
                        fs=time.perf_counter_ns(); state_cache[state_key]=features(case,fs)[0]; feature_ns=time.perf_counter_ns()-fs
                    else: feature_ns=0
                    feature_vector=state_cache[state_key]
                result=run_method(case,**setting) if args.mode in ('labels','grid') else controlled(case,**setting)
                # Independent post-response replay, outside response time, cannot rescue output.
                plan=tuple(Item(**p) for p in result['plan'])
                if result['validated']:
                    check=validate(case.effective_instance(),plan,frozen=case.frozen,cancelled=case.event.cancelled,
                        original_ids={p.task_id for p in case.reference},budget=result['B'],admissions=result['admissions_cumulative'],
                        initial=tuple(Item(**p) for p in result['initial_plan']),trace=result['trace'],
                        unchanged=tuple(Item(**p) for p in result['unchanged_outside_E']))
                    assert check.feasible,check.errors
                ins=case.effective_instance(); baseline=sum(ins.task_map[p.task_id].utility for p in case.reference if p.task_id not in case.event.cancelled)
                setting_id=([setting['w'],setting['B']] if args.mode in ('labels','grid') else
                            setting['rule']['name'] if args.mode=='rules' else [setting['threshold'],setting['time_ratio']])
                records.append(dict(base_id=row['id'],layer=row['layer'],load=label,scenario=e['scenario_index'],setting=setting_id,
                    reference_utility=baseline,features=feature_vector,feature_ns=feature_ns,result=result))
                calls+=1
        temp=dest.with_suffix('.tmp')
        with gzip.open(temp,'wt',encoding='utf-8') as f:
            for r in records: f.write(canonical_json(r)+'\n')
        temp.replace(dest)
        receipt.write_text(canonical_json(dict(sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),calls=len(records)))+'\n')
        if bi%5==0: print(json.dumps(dict(mode=args.mode,base_completed=bi+1,total_bases=len(rows),new_calls=calls,elapsed_s=(time.perf_counter_ns()-begun)/1e9)),flush=True)
    (out/'COMPLETE.json').write_text(canonical_json(dict(base_count=len(rows),full=not args.limit,mode=args.mode))+'\n')


if __name__=='__main__': main()
