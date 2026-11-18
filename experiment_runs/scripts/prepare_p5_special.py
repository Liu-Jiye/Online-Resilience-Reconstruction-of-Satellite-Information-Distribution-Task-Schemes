"""Precompute every robustness/window/anomaly input before those methods run."""
import gzip,time
from dataclasses import asdict,replace
from p5_common import *
from isl.models import case_to_dict,canonical_json
from isl.p5.data import cases,events_for,transformed,distance_contacts,window_case,anomaly_case
from isl.load_pilot import indexed_reference
from isl.validation import validate
from isl.p1_orbits import epoch

def write_input(phase,key,root,layer,cs,meta):
    path=OUT/'inputs'/phase/(key+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
    payload=dict(root_id=root,layer=layer,metadata=meta,cases=[dict(event_meta=e,case=case_to_dict(c)) for e,c in cs])
    raw=canonical_json(payload).encode()
    if path.exists():
        with gzip.open(path,'rb') as f:assert f.read()==raw,('derived input changed',key)
    else:
        tmp=path.with_suffix('.tmp')
        with gzip.open(tmp,'wb') as f:f.write(raw)
        tmp.replace(path)
    return dict(key=key,root_id=root,layer=layer,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),events=len(cs),metadata=meta)

def main():
    subsets=load(OUT/'subsets.json');manifest={r['id']:r for r in load(P4/'data/manifest.json')['instances']}
    config=load(ROOT/'configs/load_pilot_v1.json');indexes={p:[] for p in ('single_factor','windows','anomalies')};failed=[]
    for bi,ident in enumerate(subsets['special_100']):
        row=manifest[ident];d=base_data(ident);original=cases(d);base=original[0][1].base
        ref=original[0][1].reference;seed=row['seed'];layer=row['layer']
        configs=[('N',x) for x in (50,100,200,500,1000)]+[('hotspot',x) for x in (0.,.5,.8)]+[('span',x) for x in (120,300,600)]+[('rate',x) for x in (50,100,200)]+[('calendar',x) for x in (0.,.5,.8)]
        if layer!='D1':configs += [('distance',x) for x in (2000,3500,5000)]
        for factor,value in configs:
            key=ident+'__'+factor+'_'+str(value)
            contacts=None
            if factor=='distance':
                if value==5000:contacts=base.contacts
                else:
                    name='starlink' if layer=='D2-S' else 'oneweb';eligible=load(ROOT/f'data/processed/p1/{name}_eligible.json')
                    records=[r for r in eligible['records'] if str(r['NORAD_CAT_ID']) in base.satellites]
                    contacts=distance_contacts(records,epoch(eligible['t_ref_utc']),row['geometry']['offset_s'],value)
            ins=transformed(base,seed,factor,value,config,contacts)
            if factor=='N' and value==100:assert ins.tasks==base.tasks,'task-prefix fidelity'
            if factor=='hotspot' and value==0:assert ins.tasks==base.tasks
            if factor=='calendar' and value==.5:assert ins.calendar==base.calendar
            newref=indexed_reference(ins);assert validate(ins,newref).feasible
            # Empty references remain valid conditions; cancellation becomes N/A.
            events=events_for(ins,newref,seed)
            cs=cases(dict(instance=asdict(ins),reference=[asdict(p) for p in newref],events=events))
            meta=dict(factor=factor,value=value,reference_count=len(newref),original_reference_count=len(ref),reference_changed=newref!=ref,task_count=len(ins.tasks),contacts=len(ins.contacts),empty_reference=not bool(newref))
            indexes['single_factor'].append(write_input('single_factor',key,ident,layer,cs,meta))
        for ratio in (0.,.3,.6,.8):
            events=events_for(base,ref,seed,ratios=(ratio,));cs=cases(dict(instance=d['instance'],reference=d['reference'],events=events))
            indexes['single_factor'].append(write_input('single_factor',ident+'__FR_'+str(ratio),ident,layer,cs,dict(factor='FR',value=ratio,reference_count=len(ref),reference_changed=False)))
        for p,shorten in ((.1,.1),(.1,.3),(.3,.1),(.3,.3),(0.,0.),(1.,1.)):
            is_delete=p==0;target=p==1
            cs=[];details=[]
            for si,(e,c) in enumerate(original):
                new,meta=window_case(c,seed,p=p,shorten=shorten,delete=is_delete,target=target)
                assert validate(new.effective_instance(),new.frozen,frozen=new.frozen).feasible
                cs.append((e,new));details.append(meta)
            variant='targeted_pressure' if target else 'delete_one' if is_delete else f'p{p}_shrink{shorten}'
            indexes['windows'].append(write_input('windows',ident+'__'+variant,ident,layer,cs,dict(variant=variant,details=details,reference_unchanged=True)))
        if ident in subsets['frozen_anomaly_50']:
            index=subsets['frozen_anomaly_50'].index(ident);c,meta=anomaly_case(original[0][1],index)
            indexes['anomalies'].append(write_input('anomalies',ident+'__anomaly',ident,layer,[(dict(FR=.6,q=.2),c)],dict(**meta,expected_frozen_conflict=True)))
            control=replace(c,event=replace(c.event,cancelled=()) if index%2==0 else c.event,post_event_contacts=None)
            indexes['anomalies'].append(write_input('anomalies',ident+'__control',ident,layer,[(dict(FR=.6,q=.2),control)],dict(type='paired_normal_control',expected_frozen_conflict=False)))
        if bi%5==0:print(json.dumps(dict(prepared=bi+1,total=100)),flush=True)
    for phase,rows in indexes.items():sealed(OUT/'inputs'/phase/'manifest.json',dict(rows=rows,bases=len(subsets['special_100']),cases=sum(r['events'] for r in rows),failures=failed))
    save(OUT/'inputs/COMPLETE.json',dict(phase_cases={p:sum(r['events'] for r in rs) for p,rs in indexes.items()},distance_D1='not_applicable',selection_uses_outcomes=False))

if __name__=='__main__':main()
