"""Generate sealed P4 test inputs, without running any online repair method."""
from dataclasses import asdict
import json,time,zipfile
import numpy as np
from p4_common import *
from isl.models import canonical_json,case_from_dict,frozen_count
from isl.p1_generation import component_seeds,synthetic_contacts,create_instance
from isl.p1_orbits import build_contacts,epoch
from isl.load_pilot import indexed_reference
from isl.load_pilot_independent import BitAudit
from isl.events import generate_event
from isl.validation import validate

def main():
    data=OUT/'data';data.mkdir(parents=True,exist_ok=True)
    orbit={}
    for name in ('starlink','oneweb'):
        eligible=load(ROOT/f'data/processed/p1/{name}_eligible.json')
        groups=load(ROOT/f'reports/p1/{name}_groups.json')['groups']
        sets=[{i for g in groups if g['split']==s for i in g['norad_ids']} for s in ('train','validation','test')]
        assert [len(s) for s in sets]==[192,64,64]
        assert all(not(sets[i]&sets[j]) for i in range(3) for j in range(i))
        orbit[name]=(eligible,[g for g in groups if g['split']=='test'])
    generation_paths=sorted((ROOT/'src/isl').glob('*.py'))+[Path(__file__),ROOT/'scripts/p4_common.py',ROOT/'protocol/P4_EXECUTION_V1.md']
    source={p.relative_to(ROOT).as_posix():sha(p) for p in generation_paths}
    for name in ('starlink','oneweb'):
        for p in (ROOT/f'data/processed/p1/{name}_eligible.json',ROOT/f'reports/p1/{name}_groups.json'):
            source[p.relative_to(ROOT).as_posix()]=sha(p)
    frozen=data/'generation_freeze.json'
    if frozen.exists():assert load(frozen)==source
    else:save(frozen,source)
    rows=[]
    for layer,count in [('D1',400),('D2-S',300),('D2-O',300)]:
        for i in range(count):
            seed=390000+len(rows);ident=f'P4-test-{layer}-{i:04d}'
            dest=data/(ident+'.zip');receipt=data/(ident+'.json')
            if receipt.exists():
                row=load(receipt);assert sha(dest)==row['archive_sha256'];rows.append(row);continue
            start=time.perf_counter_ns()
            try:
                seeds=component_seeds(seed)
                if layer=='D1':
                    sats=tuple(f'S{i:02d}' for i in range(32))
                    contacts,_=synthetic_contacts(sats,np.random.Generator(np.random.PCG64(seeds['contacts'])))
                    geometry=dict(type='synthetic')
                else:
                    name='starlink' if layer=='D2-S' else 'oneweb';e,groups=orbit[name];g=groups[i%len(groups)]
                    ids=set(g['norad_ids']);records=[r for r in e['records'] if int(r['NORAD_CAT_ID']) in ids]
                    assert len(records)==32
                    offset=int(np.random.Generator(np.random.PCG64(seeds['segment'])).integers(-43200,37801))
                    contacts,_=build_contacts(records,epoch(e['t_ref_utc']),offset,5)
                    sats=tuple(str(n) for n in sorted(ids));geometry=dict(type=name,group=g['group_id'],offset_s=offset,step_s=5)
                ins,metadata=create_instance(ident,sats,contacts,seed)
                ref=indexed_reference(ins);assert ref==BitAudit(ins,()).reference_plan()
                assert ref,'empty reference requires explicit decision'
                assert validate(ins,ref).feasible
                events=[]
                for kind in ('cancellation','urgent_insertion','reward_update'):
                    for fr in (0.,.6):
                        for q in (.2,.8):
                            si=len(events);es=int(np.random.SeedSequence([seed,93001,si]).generate_state(1,dtype=np.uint64)[0])
                            event=generate_event(ins,ref,kind,fr,q,es)
                            events.append(dict(scenario_index=si,FR=fr,q=q,event=asdict(event)))
                payload=canonical_json(dict(instance=asdict(ins),reference=[asdict(p) for p in ref],events=events,
                        metadata=dict(instance_seed=seed,component_seeds=seeds,geometry=geometry,split='test',layer=layer,load='default'))).encode()
                temp=dest.with_suffix('.tmp')
                with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('default.json',payload)
                temp.replace(dest)
                row=dict(id=ident,seed=seed,layer=layer,geometry=geometry,archive_sha256=sha(dest),payload_sha256=__import__('hashlib').sha256(payload).hexdigest(),generation_ns=time.perf_counter_ns()-start)
                save(receipt,row);rows.append(row)
            except Exception as error:
                save(data/('FAILED-'+ident+'.json'),dict(seed=seed,error=repr(error),policy='stop_without_resampling'));raise
            if len(rows)%25==0:print(json.dumps(dict(generated=len(rows),total=1000,last=ident)),flush=True)
    save(data/'manifest.json',dict(complete=True,instances=rows,bases=1000,events=12000,source_sha256=source))
    rng=np.random.Generator(np.random.PCG64(20261020));selected=[]
    for layer,n in [('D1',40),('D2-S',30),('D2-O',30)]:
        candidates=[r['id'] for r in rows if r['layer']==layer]
        selected.extend(sorted(rng.choice(candidates,n,replace=False).tolist()))
    save(data/'timing_subset.json',dict(seed=20261020,base_ids=selected,repeats=20,events_per_base=12))
    print('P4 inputs sealed',flush=True)
if __name__=='__main__':main()
