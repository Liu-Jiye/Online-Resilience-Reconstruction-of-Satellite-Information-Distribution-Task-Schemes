"""Independent input/pairing and window-pressure certificate checks, no methods."""
import gzip
from collections import Counter,defaultdict
from p5_common import *
from isl.models import case_from_dict,case_to_dict,canonical_json
from isl.validation import validate

def payload(row):
    path=ROOT/row['path'];assert sha(path)==row['sha256']
    with gzip.open(path,'rt') as f:return json.load(f)

def main():
    sub=load(OUT/'subsets.json');manifest=load(P4/'data/manifest.json');rng=__import__('numpy').random.Generator(__import__('numpy').random.PCG64(20261020));chosen=[]
    for layer in ('D1','D2-S','D2-O'):
        ids=sorted(x['id'] for x in manifest['instances'] if x['layer']==layer);chosen+=sorted(str(x) for x in rng.choice(ids,100,replace=False))
    assert chosen==sub['ablation_300'];assert sub['special_100']==load(P4/'data/timing_subset.json')['base_ids']
    validation={r['id'] for r in load(P3/'data/manifest.json')['instances'] if r['split']=='validation'}
    assert set(sub['validation_threshold_60'])<=validation and not set(sub['special_100'])&validation
    grouped=defaultdict(list)
    for row in load(OUT/'inputs/single_factor/manifest.json')['rows']:grouped[row['root_id']].append(row)
    rows=[];counts=Counter()
    for ident,variants in grouped.items():
        from isl.p5.data import cases
        original=cases(base_data(ident))[0][1];prefix={};dist={}
        for row in variants:
            d=payload(row);c=case_from_dict(d['cases'][0]['case']);factor=row['metadata']['factor'];value=row['metadata']['value']
            a=__import__('dataclasses').asdict(c.base);b=__import__('dataclasses').asdict(original.base)
            changing={'N':'tasks','hotspot':'tasks','span':'tasks','rate':'tasks','calendar':'calendar','distance':'contacts','FR':None}[factor]
            for key in a:
                if key!=changing:assert a[key]==b[key],(ident,factor,value,key)
            if factor=='N':prefix[int(value)]=c.base.tasks
            if factor=='distance':dist[int(value)]=c.base.contacts
            if factor=='span':assert all(x.release==y.release and x.deadline==min(c.base.horizon,x.release+value) for x,y in zip(c.base.tasks,original.base.tasks))
            if factor=='rate':assert all(x.rate_bps==value*1000000 and __import__('dataclasses').replace(x,rate_bps=y.rate_bps)==y for x,y in zip(c.base.tasks,original.base.tasks))
            if factor=='FR':assert c.reference==original.reference
            assert validate(c.base,c.reference).feasible
            terminal_time=len(c.base.satellites)*c.base.horizon;busy=sum(x.end-x.start for x in c.base.calendar);planned=2*sum(x.end-x.start for x in c.reference)
            rows.append(dict(base_id=ident,layer=row['layer'],factor=factor,value=value,task_count=len(c.base.tasks),reference_count=len(c.reference),empty_reference=not bool(c.reference),reference_changed=c.reference!=original.reference,
                background_terminal_occupancy=busy/terminal_time,planned_terminal_occupancy=planned/terminal_time,
                planned_fraction_of_nonbackground_capacity=planned/max(1,terminal_time-busy),contact_count=len(c.base.contacts),
                contact_duration_mean=sum(x.end-x.start for x in c.base.contacts)/max(1,len(c.base.contacts))))
            counts['single_factor_shards']+=1
        for small,large in zip((50,100,200,500),(100,200,500,1000)):assert prefix[large][:small]==prefix[small]
        assert prefix[100]==original.base.tasks
        if dist:
            for small,large in ((2000,3500),(3500,5000)):
                for x in dist[small]:assert any((x.sender,x.receiver)==(y.sender,y.receiver) and y.start<=x.start and x.end<=y.end for y in dist[large]),(ident,small,large,x)
        counts['prefix_bases']+=1
    pressure=Counter();byvariant=defaultdict(Counter)
    for row in load(OUT/'inputs/windows/manifest.json')['rows']:
        d=payload(row);variant=row['metadata']['variant']
        for i,x in enumerate(d['cases']):
            c=case_from_dict(x['case']);meta=row['metadata']['details'][i]
            assert validate(c.effective_instance(),c.frozen,frozen=c.frozen,cancelled=c.event.cancelled).feasible
            original_survivors=tuple(p for p in c.reference if p.task_id not in c.event.cancelled)
            check=validate(c.effective_instance(),original_survivors)
            a=byvariant[variant];a['event_conditions']+=1;a['actually_changed']+=meta['changed_windows']>0;a['original_survivor_plan_lost_window']+=bool(check.window_ids)
            if variant=='targeted_pressure' and meta['changed_windows']:
                assert check.window_ids;pressure['targeted_original_placement_invalid_certificates']+=1
            counts['window_event_conditions']+=1
    anomaly=Counter()
    for row in load(OUT/'inputs/anomalies/manifest.json')['rows']:
        d=payload(row);c=case_from_dict(d['cases'][0]['case']);check=validate(c.effective_instance(),c.frozen,frozen=c.frozen,cancelled=c.event.cancelled)
        assert check.feasible!=row['metadata']['expected_frozen_conflict'];anomaly[row['metadata']['type']]+=1
    assert counts['prefix_bases']==100 and counts['window_event_conditions']==7200
    save(OUT/'input_independent_audit.json',dict(passed=True,counts=counts,paired_window_variants=byvariant,pressure_certificates=pressure,
        anomalies=anomaly,source_subsets_regenerated=True,nested_task_prefixes_verified=True,distance_monotonic_containment_verified=True,
        factor_isolation_verified=True,all_reference_plans_checked=True,source_input_hashes_checked=True))
    path=OUT/'tables/input_reference_changes.csv';path.parent.mkdir(parents=True,exist_ok=True)
    import csv
    with path.open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(dict(passed=True,counts=counts,pressure=pressure,anomalies=anomaly)),flush=True)

if __name__=='__main__':main()
