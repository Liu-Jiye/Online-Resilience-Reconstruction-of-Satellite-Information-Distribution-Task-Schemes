"""Freeze all natural and conditional pressure inputs before method runs."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import canonical_json,case_to_dict
from isl.p1_sources import save_json
from isl.urgent_supplement import base_attempt,case_for,pressure_label,pressure_event_seed


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_entry(bundle,name,data):
    payload=canonical_json(data).encode('utf-8')
    info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
    bundle.writestr(info,payload)
    return hashlib.sha256(payload).hexdigest()


def main():
    config=json.loads((ROOT/'configs/p2_urgent_supplement.json').read_text(encoding='utf-8'))
    out=ROOT/'reports/p2/P2-urgent-supplement-inputs-v1';out.mkdir(exist_ok=False)
    save_json(out/'config.json',config)
    attempts=[];valid=[];base_hashes={};case_hashes={};event_list=[]
    natural=config['natural'];pressure=config['pressure']
    with zipfile.ZipFile(out/'natural_bases.zip','w') as bundle:
        for ci,(n,s) in enumerate(natural['combination_order']):
            records=[]
            for attempt in range(natural['generation_cap_per_combination']):
                record,data=base_attempt(ci,n,s,attempt,natural['instance_seed_start'],natural['instance_seed_stride'],f'P2U-natural-c{ci}')
                attempts.append(record)
                if data:
                    records.append(record)
                    name=record['instance_id']+'.json';base_hashes[name]=write_entry(bundle,name,data)
                if len(records)==50:break
            assert len(records)==50,'Natural generation cap reached; retained partial inputs'
            valid.append(records)
            print(json.dumps({'natural_combination':ci,'attempts':attempt+1,'valid':len(records)}),flush=True)
    rng=np.random.Generator(np.random.PCG64(natural['selection_seed']))
    with zipfile.ZipFile(out/'natural_bases.zip') as bases,zipfile.ZipFile(out/'event_cases.zip','w') as cases:
        for ci,records in enumerate(valid):
            for index in rng.permutation(50).tolist()[:natural['event_counts_per_combination'][ci]]:
                record=records[index];ordinal=len(event_list)
                ratio,q=natural['FR_q_rotation'][ordinal%4]
                data=json.loads(bases.read(record['instance_id']+'.json'))
                case=case_for(data,ratio,q,natural['event_seed_start']+ordinal)
                name=f'natural-{ordinal:03d}.json';case_hashes[name]=write_entry(cases,name,case_to_dict(case))
                event_list.append({'entry':name,'cohort':'natural','ordinal':ordinal,'combination':ci,
                    'instance_id':case.base.id,'instance_seed':record['seed'],'event_seed':case.event.seed,'FR':ratio,'q':q})
    save_json(out/'natural_generation_attempts.json',attempts)
    pressure_attempts=[];pressure_summary={}
    with zipfile.ZipFile(out/'event_cases.zip','a') as cases,zipfile.ZipFile(out/'pressure_bases.zip','w') as bases:
        for gi,target in enumerate(pressure['category_order']):
            accepted=0;reasons=Counter()
            for attempt in range(pressure['attempt_cap_per_category']):
                record,data=base_attempt(gi,30,8,attempt,pressure['instance_seed_start'],pressure['instance_seed_stride'],f'P2U-pressure-g{gi}')
                ratio,q=pressure['FR_q_rotation'][attempt%4]
                record.update(target_category=target,FR=ratio,q=q)
                if data:
                    seed=pressure_event_seed(record['seed']);case=case_for(data,ratio,q,seed)
                    label=pressure_label(case)
                    record.update(event_seed=seed,label=label,accepted=label['category']==target)
                    reasons[label['category']]+=1
                    if record['accepted']:
                        name=f'pressure-g{gi}-{accepted:03d}.json'
                        full_label=pressure_label(case,full=True)
                        case_hashes[name]=write_entry(cases,name,case_to_dict(case))
                        base_name=case.base.id+'.json';base_hashes[base_name]=write_entry(bases,base_name,{'data':data,'label':full_label})
                        event_list.append({'entry':name,'cohort':'pressure','category':target,'ordinal':accepted,'group':gi,
                            'instance_id':case.base.id,'instance_seed':record['seed'],'event_seed':seed,'FR':ratio,'q':q,
                            'label':label})
                        accepted+=1
                else:
                    record['accepted']=False;reasons['generation_failed:'+record['reason']]+=1
                pressure_attempts.append(record)
                if (attempt+1)%250==0:print(json.dumps({'pressure_group':target,'attempts':attempt+1,'accepted':accepted}),flush=True)
                if accepted==pressure['target_per_category']:break
            pressure_summary[target]={'attempts':attempt+1,'accepted':accepted,'target':25,
                                      'shortfall':25-accepted,'observed_categories_and_failures':dict(reasons)}
            print(json.dumps({'pressure_group_completed':target,**pressure_summary[target]}),flush=True)
    save_json(out/'pressure_generation_attempts.json',pressure_attempts)
    save_json(out/'selected_events.json',event_list)
    summary={'natural_attempts':len(attempts),'natural_valid_bases':300,
             'natural_generation_failures':sum(a['status']!='valid' for a in attempts),
             'natural_selected_events':200,'pressure':pressure_summary,
             'pressure_selected_events':sum(v['accepted'] for v in pressure_summary.values()),
             'pressure_attempts':len(pressure_attempts),'P3_started':False,
             'selection_used_PALR_results':False,'all_new_inputs_frozen_before_solver_runs':True}
    save_json(out/'summary.json',summary)
    sources=list((ROOT/'src').rglob('*.py'))+list((ROOT/'scripts').glob('*supplement*.py'))
    sources += [ROOT/'configs/p2_urgent_supplement.json',ROOT/'protocol/P2_URGENT_SUPPLEMENT_CONTRACT.md']
    save_json(out/'manifest.json',{'study':config['study'],'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in sorted(set(sources))},
        'artifact_sha256':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()},
        'base_entry_sha256':base_hashes,'case_entry_sha256':case_hashes})
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
