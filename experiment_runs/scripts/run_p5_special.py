"""Frozen single-factor, window stress and frozen-exception paired runs."""
import gzip,time
from p5_runner import *
from isl.models import case_from_dict

def main():
    rule,stats=config()
    light=[dict(name='Minimal-Repair'),dict(name='Fixed-PALR',w=5,B=2),dict(name='Validation-Best-Fixed',w=5,B=1),dict(name='Rule-PALR')]
    for phase in ('single_factor','windows','anomalies'):
        specs=light+([dict(name='No-window',w=5,B=2,ignore_window=True),dict(name='No-receiver',w=5,B=2,ignore_receiver=True)] if phase=='windows' else [])
        manifest=load(OUT/'inputs'/phase/'manifest.json')
        freeze=frozen_phase(phase,dict(specs=specs,manifest_sha256=sha(OUT/'inputs'/phase/'manifest.json'),expected_calls=manifest['cases']*len(specs)))
        session=warm(specs,rule,stats,phase);total=0;start=time.perf_counter()
        for i,row in enumerate(manifest['rows']):
            assert sha(ROOT/row['path'])==row['sha256']
            with gzip.open(ROOT/row['path'],'rt') as f:d=json.load(f)
            cs=[(x['event_meta'],case_from_dict(x['case'])) for x in d['cases']]
            total+=collect(phase,row['key'],row['layer'],cs,specs,rule,stats,freeze,session,dict(root_id=row['root_id'],input_path=row['path'],**row['metadata']))
            if i%20==0:print(json.dumps(dict(phase=phase,shards=i+1,total_shards=len(manifest['rows']),calls=total,elapsed_s=time.perf_counter()-start)),flush=True)
        save(OUT/phase/'COMPLETE.json',dict(calls=total,shards=len(manifest['rows']),cases=manifest['cases'],freeze=freeze))

if __name__=='__main__':main()
