"""Describe frozen ET costs; benchmark training features without altering selection."""
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.p3.model_io import load_model
run=ROOT/'reports/p3/P3-20261110'

def stats(values):
    return dict(n=len(values),mean_ms=float(np.mean(values))/1e6,
                p50_p95_p99_ms=(np.percentile(values,[50,95,99])/1e6).tolist())

def main():
    begin=perf_counter_ns();model=load_model(run/'models');loading=perf_counter_ns()-begin
    selected=json.loads((run/'et_summary.json').read_text())['selected']
    observations={load:dict(control=[],total=[],success=[],failure=[]) for load in selected}
    for path in sorted((run/'et').glob('*.json.gz')):
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line);load=row['load']
                if row['setting']!=selected[load]['setting']:continue
                r=row['result'];cell=observations[load]
                cell['control'].append(r['timings_ns']['control_ns']);cell['total'].append(r['total_ns'])
                cell['success' if r['metrics']['online_success'] else 'failure'].append(r['total_ns'])
    # Timing-only benchmark: all 4000 frozen training features, 20 actions each.
    # Uses the same vectorized six-head prediction as the online implementation.
    # It is a separate cost measurement, never substituted for online total time.
    times=[];bases=0
    for path in sorted((run/'labels').glob('*.json.gz')):
        with gzip.open(path,'rt',encoding='utf-8') as stream:row=json.loads(next(stream))
        matrix=np.asarray([row['features']+[w,b] for w,b in model['actions']])
        if bases==0:
            model['classifier'].predict_proba(matrix)
            for head in model['heads']:head.predict(matrix)
        start=perf_counter_ns();model['classifier'].predict_proba(matrix)
        for head in model['heads']:head.predict(matrix)
        times.append(perf_counter_ns()-start);bases+=1
    assert bases==4000
    report=dict(model_loading_ns=loading,inference_only_training_benchmark=stats(times),
                benchmark_scope='4000 default training feature vectors, all20 actions, six frozen heads; excludes features and repair; no refit or selection',
                selected_online={load:{key:stats(vals) for key,vals in cell.items()} for load,cell in observations.items()},
                control_scope='actual recorded online control, including feature extraction, prediction, selection and dispatch; not inference alone',
                test_instances=0)
    (run/'et_cost_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('ET cost audit complete',flush=True)

if __name__=='__main__':main()
