"""Frozen300, all12 scenarios. Grid is explicitly offline, never timed as one action."""
import time
from p5_runner import *

def specs():
    jobs=[]
    for w in (1,3,5,10,20):
        for b in (0,1,2,3,5):jobs.append(dict(name=f'Grid-w{w}-B{b}',w=w,B=b,role='A3/A4/A9-offline-grid'))
    jobs += [dict(name=n) for n in ('Minimal-Repair','Rule-PALR','B-only','w-only')]
    jobs += [dict(name='No-window',w=5,B=2,ignore_window=True),dict(name='No-receiver',w=5,B=2,ignore_receiver=True),dict(name='Insert-only',w=5,B=2,insertion_only=True)]
    jobs += [dict(name='Random-ties',w=5,B=2,random_ties=True,seed=s) for s in SEEDS]
    jobs += [dict(name=n,budget_ms=b) for b in (5,10,20,50,100) for n in ('Rule-PALR','No-time')]
    # Rule50 is a separate A10 paired call, not a replacement of A5 record.
    for i,j in enumerate(jobs):j['spec_id']=i
    return jobs

def main():
    subset=load(OUT/'subsets.json');rule,stats=config();jobs=specs()
    freeze=frozen_phase('ablations',dict(specs=jobs,expected_bases=300,expected_calls=300*12*len(jobs)))
    session=warm(jobs,rule,stats,'ablations');n=0;start=time.perf_counter()
    for i,ident in enumerate(subset['ablation_300']):
        n+=collect('ablations',ident,subset['layers'][ident],cases(base_data(ident)),jobs,rule,stats,freeze,session)
        if i%5==0:print(json.dumps(dict(phase='ablations',bases=i+1,total=300,calls=n,elapsed_s=time.perf_counter()-start)),flush=True)
    save(OUT/'ablations/COMPLETE.json',dict(bases=300,calls=n,specs=len(jobs),freeze=freeze))

if __name__=='__main__':main()
