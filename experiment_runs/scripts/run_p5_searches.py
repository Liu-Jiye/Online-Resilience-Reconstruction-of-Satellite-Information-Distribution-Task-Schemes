"""Development threshold, same-domain mechanisms, simulations and upgrade tests."""
import gzip,time
from p5_runner import *

def calibration():
    rule,stats=config();sub=load(OUT/'subsets.json');jobs=[dict(name='Fixed-PALR',w=5,B=2,budget_ms=10)]
    freeze=frozen_phase('calibration',dict(specs=jobs,validation_bases=sub['validation_threshold_60']))
    session=warm(jobs,rule,stats,'calibration');values=[];den=0
    for ident in sub['validation_threshold_60']:
        d=base_data(ident,P3);cs=cases(d)
        collect('calibration',ident,d['metadata']['layer'],cs,jobs,rule,stats,freeze,session)
        with gzip.open(OUT/'calibration'/(ident+'.json.gz'),'rt') as f:
            for line in f:
                r=json.loads(line);c=cs[r['scenario']][1];m=r['result']['metrics']
                tm=c.effective_instance().task_map;u=sum(tm[p.task_id].utility for p in c.reference if p.task_id not in c.event.cancelled)
                values.append((bool(c.event.urgent) and not m['service_success'],m['U_raw']/max(1,u) if r['result']['validated'] else 0.));den+=1
    candidates=[dict(threshold=t,trigger_rate=sum(fail or ratio<t for fail,ratio in values)/den) for t in (.95,1.)]
    chosen=min(candidates,key=lambda c:(abs(c['trigger_rate']-.2),c['threshold']))
    sealed(OUT/'upgrade_threshold.json',dict(**chosen,candidates=candidates,validation_events=den,policy='closest trigger rate to0.2, lower threshold on tie',test_used=False,source_freeze=freeze))
    save(OUT/'calibration/COMPLETE.json',dict(bases=60,calls=den,freeze=freeze));return chosen['threshold']

def main():
    threshold=calibration();sub=load(OUT/'subsets.json');rule,stats=config()
    phases={
        'mechanisms':[dict(name='PALR-local',w=5,B=2),dict(name='CP-local')]+[dict(name=n,local_w=5,B=2,seed=s) for n in ('PUCT-local','ALNS-local') for s in SEEDS],
        'simulations':[dict(name='PUCT-sensitivity',simulations=n,seed=s) for n in (40,100,400) for s in SEEDS],
        'upgrades':[dict(name='PALR-only',w=5,B=2)]+[dict(name=n,seed=s,threshold=threshold) for n in ('PUCT-only','ALNS-only','Upgrade-PUCT','Upgrade-ALNS') for s in SEEDS]
    }
    for phase,jobs in phases.items():
        freeze=frozen_phase(phase,dict(specs=jobs,expected_calls=100*12*len(jobs),threshold_receipt=sha(OUT/'upgrade_threshold.json')))
        session=warm(jobs,rule,stats,phase);n=0;start=time.perf_counter()
        for i,ident in enumerate(sub['special_100']):
            n+=collect(phase,ident,sub['layers'][ident],cases(base_data(ident)),jobs,rule,stats,freeze,session)
            if i%5==0:print(json.dumps(dict(phase=phase,bases=i+1,calls=n,elapsed_s=time.perf_counter()-start)),flush=True)
        save(OUT/phase/'COMPLETE.json',dict(bases=100,calls=n,freeze=freeze))

if __name__=='__main__':main()
