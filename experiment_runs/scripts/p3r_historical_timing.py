"""Describe frozen selected P3 records; no fitting or revised validation."""
from collections import defaultdict
import gzip,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112'
def main():
    params=json.loads((P3/'frozen_parameters.json').read_text())['parameters'];groups=defaultdict(list)
    for mode in ('grid','rules','et','search'):
        for i,p in enumerate(sorted((P3/mode).glob('*.json.gz'))):
            with gzip.open(p,'rt') as f:
                for l in f:
                    r=json.loads(l);cfg=params[r['load']];setting=r['setting']
                    if mode=='grid' and setting!=[cfg['fixed']['w'],cfg['fixed']['B']]:continue
                    if mode=='rules' and setting!=cfg['rule']['name']:continue
                    if mode=='et' and setting!=[cfg['ET']['probability'],cfg['ET']['time_safety_ratio']]:continue
                    if mode=='search' and setting[0]=='PUCT' and setting[1]!=cfg['PUCT']['temperature']:continue
                    name=setting[0].lower() if mode=='search' else {'grid':'fixed','rules':'rule','et':'et_original'}[mode]
                    result=r['result'];m=result['metrics']
                    groups[name,r['load']].append(dict(total_ns=result['total_ns'],timings_ns=result['timings_ns'],
                        online_success=m['online_success'],service_success=m['service_success'],strict_feasible=m['strict_feasible'],
                        timeout=result['status']=='timeout'))
            if i%200==0:print('historical timing',mode,i,flush=True)
    output={}
    for (method,load),rs in groups.items():
        timing_keys=sorted({k for r in rs for k in r['timings_ns']})
        def summary(vals):return dict(mean_ms=float(np.mean(vals)/1e6),p50_p95_p99_ms=(np.percentile(vals,[50,95,99])/1e6).tolist())
        output[method+'/'+load]=dict(n=len(rs),total=summary([r['total_ns'] for r in rs]),
            components={k:summary([r['timings_ns'].get(k,0) for r in rs]) for k in timing_keys},
            timeouts=sum(r['timeout'] for r in rs),valid_but_late=sum(r['strict_feasible'] and r['timeout'] for r in rs),
            feasible_but_unserved=sum(r['strict_feasible'] and not r['service_success'] for r in rs),
            caution='component timers can be incomplete after cooperative deadline; percentiles are not additive; no physical infeasibility certificate')
    (OUT/'historical_timing_decomposition.json').write_text(json.dumps(output,indent=2)+'\n')
if __name__=='__main__':main()
