"""Generate/freeze 300 P2 bases and a prespecified list of 200 events."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0,str(ROOT/'src'))
from isl.models import canonical_json,case_to_dict
from isl.p1_sources import save_json
from isl.p2_generation import generate_base,select_events,make_case


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config=json.loads((ROOT/'configs/p2.json').read_text(encoding='utf-8'))
    out=ROOT/'reports/p2/P2-inputs-v1'
    out.mkdir(parents=True,exist_ok=False)
    save_json(out/'config.json',config)
    attempts,valid_by_combination,payloads=[],[],{}
    for ci,(n,s) in enumerate(config['combination_order']):
        valid=[]
        for attempt in range(1000):
            record,data=generate_base(ci,n,s,attempt,config)
            attempts.append(record)
            if data:
                valid.append(record);payloads[record['instance_id']]=data
            if len(valid)==50:break
        assert len(valid)==50,'Generation cap reached; retain evidence and request user decision'
        valid_by_combination.append(valid)
        print(json.dumps({'combination':[n,s],'attempts':attempt+1,'valid':len(valid)}),flush=True)
    events=select_events(valid_by_combination,config)
    save_json(out/'generation_attempts.json',attempts)
    save_json(out/'selected_events.json',events)
    entry_hashes={}
    with zipfile.ZipFile(out/'base_instances.zip','w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for iid,data in sorted(payloads.items()):
            payload=canonical_json(data).encode('utf-8')
            name=iid+'.json'
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            bundle.writestr(info,payload);entry_hashes[name]=hashlib.sha256(payload).hexdigest()
    case_hashes={}
    with zipfile.ZipFile(out/'event_cases.zip','w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for spec in events:
            case=make_case(payloads[spec['instance_id']],spec)
            payload=canonical_json(case_to_dict(case)).encode('utf-8')
            name=f"event-{spec['event_ordinal']:03d}.json"
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            bundle.writestr(info,payload);case_hashes[name]=hashlib.sha256(payload).hexdigest()
    summary={'attempts':len(attempts),'valid_bases':len(payloads),'generation_failures':sum(r['status']!='valid' for r in attempts),
             'failure_reasons':dict(Counter(r['reason'] for r in attempts if r['status']!='valid')),
             'event_count':len(events),'distinct_selected_bases':len({e['instance_id'] for e in events}),
             'kind_counts':dict(Counter(e['kind'] for e in events)),
             'scenario_counts':dict(Counter(f"{e['kind']}:FR={e['FR']}:q={e['q']}" for e in events)),
             'combination_kind_counts':dict(Counter(f"{e['combination_index']}:{e['kind']}" for e in events)),
             'test_instances_generated':0,'selection_used_solver_or_heuristic_performance':False}
    save_json(out/'summary.json',summary)
    sources=list((ROOT/'src').rglob('*.py'))+list((ROOT/'tests').glob('*.py'))+list((ROOT/'scripts').glob('*p2.py'))
    sources += [ROOT/'configs/p2.json',ROOT/'protocol/P2_EXACT_CONTRACT.md',ROOT/'environment/requirements-p2.lock.txt']
    save_json(out/'manifest.json',{'stage':'P2','input_frozen_before_solver_runs':True,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in sorted(set(sources))},
        'artifact_sha256':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()},
        'base_entry_sha256':entry_hashes,'case_entry_sha256':case_hashes})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
