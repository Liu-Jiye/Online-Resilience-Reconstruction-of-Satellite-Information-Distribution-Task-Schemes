"""Linux-only fixed-budget supplementary labels and two predetermined models."""
import gzip,hashlib,json,platform,sys,time,zipfile
from pathlib import Path
import joblib,numpy as np
from sklearn.ensemble import ExtraTreesClassifier
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict,frozen_count,Item,canonical_json
from isl.validation import validate
from isl.p3r.control import features,rule_action
from isl.p3r.indexed import IndexedInstance,earliest
from isl.p3r.repair_runtime import run_method
from isl.p3r.sparse_control import ACTIONS,PARAMS
P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112'

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replay(case,r):
    if r['validated']:
        check=validate(case.effective_instance(),tuple(Item(**p) for p in r['plan']),frozen=case.frozen,
            cancelled=case.event.cancelled,original_ids={p.task_id for p in case.reference},budget=r['B'],
            admissions=r['admissions_cumulative'],initial=tuple(Item(**p) for p in r['initial_plan']),
            trace=r['trace'],unchanged=tuple(Item(**p) for p in r['unchanged_outside_E']))
        assert check.feasible,check.errors
def label_key(r):
    m=r['result']['metrics']
    return (not m['online_success'],-m['U_exec']/max(1,r['reference_utility']),m['N_drop'],m['N_add'],m['M_all'],r['result']['total_ns'])
def main():
    assert platform.system()=='Linux','Formal training must use frozen P3 Linux image'
    gate=load(OUT/'training_gate_linux.json');assert gate['formal_linux_gate'] and gate['exact_behavior_checks']==288
    for name,h in gate['source_sha256'].items():assert sha(ROOT/name)==h,('training gate source changed',name)
    assert not (OUT/'validation').exists(),'Do not retrain after validation starts'
    frozen=load(P3/'frozen_parameters.json')['parameters']
    rows=load(P3/'data/manifest.json')['instances'];supp=[]
    for layer in ('D1','D2-S','D2-O'):supp += [r for r in rows if r['split']=='train' and r['layer']==layer][:200]
    # This budget is fixed before collecting any new label, independent of performance.
    budget=dict(training_ids=[r['id'] for r in supp],load='N500-h0.8',scenario='global_index%12',actions=ACTIONS,records=2400)
    budget_path=OUT/'supplement_budget.json'
    if budget_path.exists():assert load(budget_path)==json.loads(json.dumps(budget))
    else:budget_path.write_text(json.dumps(budget,indent=2)+'\n')
    labels=OUT/'supplement_labels';labels.mkdir(exist_ok=True)
    source={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src/isl/p3r').glob('*.py'))+[Path(__file__),P3/'data/manifest.json']}
    source_path=labels/'source_freeze.json'
    if source_path.exists():assert load(source_path)==source,'Cannot mix supplementary label sources'
    else:source_path.write_text(json.dumps(source,indent=2)+'\n')
    for bi,row in enumerate(supp):
        dest=labels/(row['id']+'.json.gz');receipt=dest.with_suffix('.receipt.json')
        if receipt.exists():assert load(receipt)['sha256']==sha(dest);continue
        with zipfile.ZipFile(P3/'data'/(row['id']+'.zip')) as z:d=json.loads(z.read('N500-h0.8.json'))
        e=d['events'][row['global_index']%12]
        case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
        start=time.perf_counter_ns();x,meta=features(case,start);feature_ns=time.perf_counter_ns()-start
        tm=case.effective_instance().task_map;utility=sum(tm[p.task_id].utility for p in case.reference if p.task_id not in case.event.cancelled)
        records=[]
        for w,B in ACTIONS:
            result=run_method(case,w=w,B=B);replay(case,result)
            records.append(dict(base_id=row['id'],load='N500-h0.8',features=x,feature_meta=meta,feature_ns=feature_ns,setting=[w,B],reference_utility=utility,result=result))
        with gzip.open(dest,'wt') as f:
            for r in records:f.write(canonical_json(r)+'\n')
        receipt.write_text(json.dumps(dict(sha256=sha(dest),calls=4))+'\n')
        if bi%50==0:print('supplement labels',bi+1,'/600',flush=True)
    xs=[];ya=[];yd=[];groups=[];costs=dict(old_records=0,new_records=0,new_label_response_ns=0,new_feature_ns=0)
    for label_dir,load_name in ((P3/'labels','default'),(labels,'N500-h0.8')):
        for p in sorted(label_dir.glob('*.json.gz')):
            with gzip.open(p,'rt') as f:rs=[json.loads(l) for l in f]
            assert len(rs)==(20 if load_name=='default' else 4)
            assert all(r['base_id'].startswith('P3-train-') and r['load']==load_name for r in rs)
            costs['old_records' if load_name=='default' else 'new_records']+=len(rs)
            if load_name!='default':
                costs['new_label_response_ns']+=sum(r['result']['total_ns'] for r in rs)
                costs['new_feature_ns']+=rs[0]['feature_ns']
            by_action={tuple(r['setting']):r for r in rs}
            available=[(i,by_action[a]) for i,a in enumerate(ACTIONS)]
            chosen,best=min(available,key=lambda ir:(label_key(ir[1]),ir[0]))
            if not best['result']['metrics']['online_success']:chosen=-1
            x=list(rs[0]['features']);meta=dict(n_feas=x[3],complete=True if load_name=='default' else rs[0]['feature_meta']['complete'],urgent_opportunity=False)
            # Reuse recorded online features; rules with B=0 have no old positive-budget label.
            if x[0]==1:
                base_row=next(r for r in rows if r['id']==rs[0]['base_id'])
                with zipfile.ZipFile(P3/'data'/(base_row['id']+'.zip')) as z:d=json.loads(z.read(load_name+'.json'))
                e=d['events'][base_row['global_index']%12]
                case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                meta['urgent_opportunity']=earliest(IndexedInstance(case.effective_instance()),case.event.urgent,case.frozen) is not None
            rule=rule_action(x,meta,frozen[load_name]['rule'])
            rule_row=by_action.get(tuple(rule))
            dev=chosen if chosen>=0 and rule_row is not None and label_key(best)<label_key(rule_row) else -1
            x[5]=1.;xs.append(x);ya.append(chosen);yd.append(dev);groups.append(rs[0]['base_id'])
    assert costs['old_records']==80000 and costs['new_records']==2400
    models=OUT/'models';models.mkdir(exist_ok=True);info={}
    for mode,y in (('action',ya),('deviation',yd)):
        start=time.perf_counter_ns();model=ExtraTreesClassifier(**PARAMS).fit(np.asarray(xs),np.asarray(y))
        path=models/(mode+'.joblib');joblib.dump(model,path,compress=3)
        vals,counts=np.unique(y,return_counts=True)
        info[mode]=dict(sha256=sha(path),bytes=path.stat().st_size,fit_and_save_ns=time.perf_counter_ns()-start,label_counts=dict(zip(map(str,vals),map(int,counts))))
    (models/'index.json').write_text(json.dumps(dict(params=PARAMS,actions=ACTIONS,files=info,costs=costs,states=len(xs),independent_training_bases=len(set(groups)),validation_used=False),indent=2)+'\n')
    print('two candidates trained on training inputs only',flush=True)
if __name__=='__main__':main()
