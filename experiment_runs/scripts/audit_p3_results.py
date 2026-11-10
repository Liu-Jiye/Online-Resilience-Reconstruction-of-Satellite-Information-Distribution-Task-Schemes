"""Final integrity/scoring audit plus preseeded independent constraint replays.

Every validated response already underwent original-validator replay during
generation. This audit verifies all immutable records and independently samples
2000 outputs per mode; it cannot turn late/failed outputs into successes.
"""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count,Item
from isl.validation import validate
run=ROOT/'reports/p3/P3-20261110';start=time.perf_counter_ns();reports={}
expected=dict(labels=(4000,80000),grid=(1000,600000),rules=(1000,72000),et=(1000,144000),search=(1000,96000))
for mi,(mode,(bases,calls)) in enumerate(expected.items()):
    folder=run/mode;complete=json.loads((folder/'COMPLETE.json').read_text())
    assert complete['full'] and complete['base_count']==bases
    frozen=json.loads((folder/'source_freeze.json').read_text())
    for name,h in frozen.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    chosen=set(int(i) for i in np.random.Generator(np.random.PCG64(93005+mi)).choice(calls,2000,replace=False))
    count=0;replays=0;timeouts=0;failed=0;validated=0;by_cell=Counter();feature_incomplete=0
    files=sorted(folder.glob('*.json.gz'));assert len(files)==bases
    for path in files:
        receipt=json.loads(path.with_suffix('.receipt.json').read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256']
        ident=path.name[:-8];cases={};perfile=0
        with zipfile.ZipFile(run/'data'/(ident+'.zip')) as z:
            datasets={n[:-5]:json.loads(z.read(n)) for n in z.namelist()}
        with gzip.open(path,'rt',encoding='utf-8') as f:
            for line in f:
                row=json.loads(line);r=row['result'];m=r['metrics'];key=(row['load'],row['scenario'])
                if key not in cases:
                    d=datasets[key[0]];e=d['events'][key[1]]
                    c=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    cases[key]=(c,c.effective_instance().task_map,{p.task_id:p for p in c.reference})
                case,tasks,before=cases[key];after={p['task_id']:p for p in r['plan']}
                U=sum(tasks[tid].utility for tid in after)
                assert U==m['U_raw']
                ontime=r['total_ns']<=50_000_000
                assert m['within_budget']==ontime
                assert m['U_exec']==(U if m['applicable'] and m['strict_feasible'] and ontime else 0)
                service=case.event.urgent is None or case.event.urgent.id in after
                assert m['online_success']==bool(m['applicable'] and m['strict_feasible'] and service and ontime)
                assert m['valid_output']==bool(m['applicable'] and m['strict_feasible'] and ontime)
                surviving=set(before)-set(case.event.cancelled)-set(r['forced_removed'])
                assert m['N_drop']==len(surviving-set(after))
                assert m['N_add']==len(set(after)-set(before))
                assert m['M_all']==sum(abs(after[t]['start']-before[t].start) for t in surviving & set(after))
                assert sum(r['timings_ns'].values())==r['total_ns']
                assert 0<=r['admissions_cumulative']<=r['B']<=5
                if count in chosen:
                    if r['validated']:
                        check=validate(case.effective_instance(),tuple(Item(**p) for p in r['plan']),frozen=case.frozen,cancelled=case.event.cancelled,
                            original_ids=set(before),budget=r['B'],admissions=r['admissions_cumulative'],
                            initial=tuple(Item(**p) for p in r['initial_plan']),trace=r['trace'],unchanged=tuple(Item(**p) for p in r['unchanged_outside_E']))
                        assert check.feasible,check.errors
                    replays+=1
                count+=1;perfile+=1;validated+=r['validated'];timeouts+=r['status']=='timeout';failed+=not m['online_success']
                if mode!='labels':by_cell[(row['load'],row['layer'],row['scenario'])]+=1
                feature_incomplete+=bool(r.get('controller_meta',{}).get('complete') is False)
        assert perfile==receipt['calls']
    assert count==calls and replays==2000
    if mode!='labels':assert len(by_cell)==72
    reports[mode]=dict(records=count,base_files=bases,sampled_independent_replays=replays,
                       validated=validated,timeouts=timeouts,not_online_success=failed,incomplete_controller_feature_census=feature_incomplete)
    print(mode,'audit passed',count,flush=True)
model=json.loads((run/'models/index.json').read_text())
for name,record in model['files'].items():
    p=run/'models'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256']
assert model['training_records']==80000 and model['training_bases']==4000
report=dict(passed=True,modes=reports,total_records=sum(v['records'] for v in reports.values()),
            original_validator_replay_at_generation='every validated response, asserted before shard receipt',
            additional_sample_replays=10000,model_hashes_passed=True,test_instances=0,P4_started=False,
            elapsed_ns=time.perf_counter_ns()-start)
(run/'final_audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('P3 final audit complete',flush=True)
