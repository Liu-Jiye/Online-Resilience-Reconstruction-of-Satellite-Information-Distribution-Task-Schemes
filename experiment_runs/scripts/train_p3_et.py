"""Fit six separately frozen ET heads, training partition only."""
import gzip
import hashlib
import json
from pathlib import Path
import time
import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier,ExtraTreesRegressor
ROOT=Path(__file__).resolve().parents[1]
run=ROOT/'reports/p3/P3-20261110'
cfg=json.loads((ROOT/'configs/p3_v1.json').read_text())
assert json.loads((run/'labels/COMPLETE.json').read_text())['full']
xs=[]; ys=[]; groups=[]; label_ns=0; feature_ns=0; density=[]
for path in sorted((run/'labels').glob('*.json.gz')):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:
            row=json.loads(line); m=row['result']['metrics']
            assert row['load']=='default' and row['base_id'].startswith('P3-train-')
            xs.append(row['features']+row['setting'])
            ys.append([int(m['online_success']),m['U_raw']-row['reference_utility'],m['N_drop'],m['N_add'],m['M_all'],row['result']['total_ns']/1e6])
            groups.append(row['base_id']);label_ns+=row['result']['total_ns'];feature_ns+=row['feature_ns']
assert len(xs)==80000 and len(set(groups))==4000
X=np.asarray(xs); Y=np.asarray(ys); out=run/'models';out.mkdir(exist_ok=False)
params=dict(n_estimators=200,max_depth=12,min_samples_leaf=5,max_features=1.0,random_state=20261020,n_jobs=1)
started=time.perf_counter_ns(); costs={}; hashes={}
heads=['utility_gain','drops','adds','movement','latency_ms']
for i,name in enumerate(['classifier']+heads):
    before=time.perf_counter_ns()
    estimator=ExtraTreesClassifier(**params,class_weight='balanced') if i==0 else ExtraTreesRegressor(**params)
    estimator.fit(X,Y[:,i].astype(int) if i==0 else Y[:,i])
    costs[name]=time.perf_counter_ns()-before
    path=out/(name+'.joblib');joblib.dump(estimator,path,compress=3)
    hashes[path.name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
    print(name,'trained_seconds',costs[name]/1e9,'bytes',path.stat().st_size,flush=True)
actions=[(w,b) for w in cfg['w'] for b in cfg['B'] if b>0]
index=dict(actions=actions,heads=heads,params=params,class_weight='balanced_train_only',training_records=len(xs),training_bases=4000,
           training_ns=costs,total_training_wall_ns=time.perf_counter_ns()-started,label_response_ns=label_ns,feature_extraction_ns=feature_ns,
           files=hashes,success_labels=np.bincount(Y[:,0].astype(int),minlength=2).tolist(),
           isolation='only default training bases; all20 actions of eachbase kept together; no validation fitting')
(out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
