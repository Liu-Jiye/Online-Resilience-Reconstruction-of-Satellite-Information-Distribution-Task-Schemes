"""Validation calibration audit only; never refit a model or alter a threshold."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.p3.model_io import load_model
run=ROOT/'reports/p3/P3-20261110'; model=load_model(run/'models');start=time.perf_counter_ns()
assert json.loads((run/'grid/COMPLETE.json').read_text())['full']
bins=defaultdict(lambda:np.zeros((10,4)));counts=defaultdict(int)
X=[];labels=[];groups=[]


def consume():
    if not X:return
    classifier=model['classifier'];prob=classifier.predict_proba(np.asarray(X));classes=list(classifier.classes_)
    ps=prob[:,classes.index(1)] if 1 in classes else np.zeros(len(X))
    for p,y,(load,kind) in zip(ps,labels,groups):
        for key in (load,load+'/'+kind):
            index=min(9,int(p*10));bins[key][index]+=np.asarray([1,p,y,(p-y)**2]);counts[key]+=1
    X.clear();labels.clear();groups.clear()


for path in sorted((run/'grid').glob('*.json.gz')):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            if r['setting'][1]==0:continue
            X.append(r['features']+r['setting']);labels.append(int(r['result']['metrics']['online_success']))
            groups.append((r['load'],('cancellation','urgent_insertion','reward_update')[r['scenario']//4]))
            if len(X)>=10000:consume()
consume()
report={}
for group,values in bins.items():
    N=counts[group];rows=[];ece=0.
    for i,(n,p,y,brier) in enumerate(values):
        if n:ece+=abs(p/n-y/n)*n/N
        rows.append(dict(bin=i,n=int(n),mean_probability=p/n if n else None,observed_success=y/n if n else None))
    report[group]=dict(n=N,brier=float(values[:,3].sum()/N),ECE10=float(ece),bins=rows)
assert counts['default']==240000 and counts['N500-h0.8']==240000
(run/'et_calibration.json').write_text(json.dumps(dict(groups=report,cost_ns=time.perf_counter_ns()-start,
    refitted=False,scope='all20 positive-budget validation grid actions; balanced training classifier; no probability recalibration fitted'),indent=2)+'\n')
print('Calibration audit complete',flush=True)
