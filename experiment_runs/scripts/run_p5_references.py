"""100 initial CP30 references, full native models/responses, shared follow-up cases."""
import gzip,time
from dataclasses import asdict
from p5_runner import *
from isl.p5.solver import reference_cp
from isl.p5.data import events_for

def main():
    sub=load(OUT/'subsets.json');rule,stats=config()
    jobs=[dict(name='Minimal-Repair'),dict(name='Fixed-PALR',w=5,B=2),dict(name='Validation-Best-Fixed',w=5,B=1),dict(name='Rule-PALR')]
    freeze=frozen_phase('references',dict(specs=jobs,reference_ids=sub['reference_100'],cp_limit_s=30))
    session=warm(jobs,rule,stats,'references');results=[];n=0
    manifest={r['id']:r for r in load(P4/'data/manifest.json')['instances']}
    for i,ident in enumerate(sub['reference_100']):
        d=base_data(ident);c=cases(d)[0][1];dest=OUT/'references/initial_cp'/(ident+'.json.gz');receipt=dest.with_suffix('.receipt.json')
        if receipt.exists():
            assert sha(dest)==load(receipt)['sha256']
            with gzip.open(dest,'rt') as f:r=json.load(f)
        else:
            r=reference_cp(c.base,c.reference);dest.parent.mkdir(parents=True,exist_ok=True)
            with gzip.open(dest,'wt') as f:f.write(canonical_json(r))
            save(receipt,dict(sha256=sha(dest),freeze=freeze))
        summary={k:v for k,v in r.items() if k not in ('model_text','response_text','plan')};summary['base_id']=ident;results.append(summary)
        if r['plan'] is not None:
            ref=tuple(Item(**p) for p in r['plan']);assert validate(c.base,ref).feasible
            events=events_for(c.base,ref,manifest[ident]['seed']);payload=dict(instance=d['instance'],reference=r['plan'],events=events)
            path=OUT/'references/inputs'/(ident+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                with gzip.open(path,'wt') as f:f.write(canonical_json(payload))
            n+=collect('references',ident,sub['layers'][ident],cases(payload),jobs,rule,stats,freeze,session,dict(reference_source='CP-SAT30',input_path=path.relative_to(ROOT).as_posix(),reference_status=r['status']))
        if i%5==0:print(json.dumps(dict(phase='references',bases=i+1,calls=n,status=r['status'],cp_seconds=r['total_ns']/1e9)),flush=True)
    save(OUT/'references/initial_reference_summary.json',dict(attempts=100,results=results))
    save(OUT/'references/COMPLETE.json',dict(attempts=100,successful_references=sum(r['status'] in ('OPTIMAL','FEASIBLE') for r in results),calls=n,freeze=freeze))

if __name__=='__main__':main()
