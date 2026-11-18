"""Seal P5 subsets without reading method scores."""
import numpy as np
from p5_common import *

def main():
    manifest=load(P4/'data/manifest.json');rng=np.random.Generator(np.random.PCG64(20261020))
    chosen=[]
    for layer in ('D1','D2-S','D2-O'):
        ids=sorted(r['id'] for r in manifest['instances'] if r['layer']==layer)
        chosen+=sorted(str(x) for x in rng.choice(ids,100,replace=False))
    hundred=load(P4/'data/timing_subset.json')['base_ids']
    byid={r['id']:r for r in manifest['instances']}
    training=load(P3/'data/manifest.json')['instances']
    validation=[]
    for layer in ('D1','D2-S','D2-O'):
        validation += [r['id'] for r in training if r['split']=='validation' and r['layer']==layer][:20]
    subset=dict(version='P5-v1',rng='PCG64',seed=20261020,ablation_300=chosen,special_100=hundred,
                frozen_anomaly_50=hundred[:50],continuous_100=hundred,reference_100=hundred,
                validation_threshold_60=validation,cross_constellation_test=[i for i in hundred if byid[i]['layer']=='D2-O'],
                layers={i:byid[i]['layer'] for i in sorted(set(chosen+hundred))},
                source_sha256={'P4_manifest':sha(P4/'data/manifest.json'),'P4_timing_subset':sha(P4/'data/timing_subset.json')},
                selection_reads_method_scores=False,ET='not_applicable_user_confirmed',A6='not_applicable_user_confirmed')
    sealed(OUT/'subsets.json',subset)
    # Every previously tracked byte is recorded before any P5 changes to navigation.
    import subprocess
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT.parent).decode().split('\0')
    history={}
    for rel in tracked:
        if rel.startswith('experiment_runs/') and (ROOT.parent/rel).is_file():history[rel]=sha(ROOT.parent/rel)
    sealed(OUT/'historical_bytes.json',history)
    print('P5 subsets sealed: 300 ablations; 100 specials; 50 anomalies; 60 development threshold bases')

if __name__=='__main__':main()
