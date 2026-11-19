"""P6 paired 10,000-draw inference from immutable P4/P5 event evidence."""
import hashlib
import numpy as np
import pandas as pd
from p6_common import *
from p6_bootstrap import Bootstrap,ratio,interval

METRICS={'online_success':('online_success','applicable'),'strict_feasible':('strict_app','applicable'),
 'valid_output':('valid_output','applicable'),'U_exec':('U_exec','applicable'),
 'timeout_rate':('timeout_app','applicable'),'latency_mean_ms':('latency_app','applicable'),
 'online_urgent_service':('online_urgent','applicable_urgent'),
 'conditional_U':('accepted_U_raw','valid_output')}
METRICS.update({'conditional_'+k:('accepted_'+k,'valid_output') for k in ['N_drop','N_add','N_sym','M_all','M_edit','N_forced']})
EFFECT_METRICS=['online_success','U_exec','timeout_rate','conditional_U','conditional_N_drop','conditional_M_all']
CACHE={}
def bootstrap(ids):
    key=tuple(sorted(ids))
    if key not in CACHE:CACHE[key]=Bootstrap(key,metadata())
    return CACHE[key]

def pairs(name,labels):
    labels=set(labels);p=[]
    def add(a,b):
        if a in labels and b in labels and a!=b and (a,b) not in p:p.append((a,b))
    if name=='P4':
        for a in ['Rule-PALR','Fixed-PALR','Validation-Best-Fixed']:
            for b in sorted(labels):
                if a=='Rule-PALR' or b in ['Minimal-Repair','PUCT-ISL','ALNS-ISL','CP-SAT-50ms']:add(a,b)
    elif name=='mechanisms':
        for b in sorted(labels):add('PALR-local',b)
    elif name=='simulations':
        for a in sorted(labels):add(a,'PUCT-sensitivity@sim40')
    elif name=='upgrades':
        for a,b in [('Upgrade-PUCT','PALR-only'),('Upgrade-ALNS','PALR-only'),('Upgrade-PUCT','PUCT-only'),('Upgrade-ALNS','ALNS-only')]:add(a,b)
    elif name=='ablations':
        for b in ['Minimal-Repair','Grid-w5-B2','Grid-w5-B1','B-only','w-only']:add('Rule-PALR',b)
        for a in ['Insert-only','Random-ties','No-window','No-receiver']:add(a,'Grid-w5-B2')
        for a in sorted(labels):
            if a.startswith('Grid-'):add(a,'Grid-w5-B2')
        for t in [5,10,20,50,100]:add(f'Rule-PALR@{t}ms',f'No-time@{t}ms')
    else:
        for b in sorted(labels):add('Rule-PALR',b)
        add('Fixed-PALR','Minimal-Repair')
        for a in ['No-window','No-receiver']:add(a,'Fixed-PALR')
    return p

def masks(e,name):
    yield 'overall','all',e
    dims=[['layer'],['kind']]
    if name=='P4':dims += [['FR'],['q'],['layer','kind','FR','q']]
    for ds in dims:
        for k,g in e.groupby(ds,dropna=False):
            k=k if isinstance(k,tuple) else (k,)
            yield '+'.join(ds),'|'.join(str(v) for v in k),g

def infer_view(e,b,phase,condition,view,stratum):
    e=e.copy();e['strict_app']=e.strict_feasible*e.applicable
    e['timeout_app']=e.timeout*e.applicable;e['latency_app']=e.total_ms*e.applicable
    labels=sorted(e.label.unique());fields=sorted(set(x for nd in METRICS.values() for x in nd))
    arrays=[];column={};stats=[];effects=[];reps={};point={};repvalues={}
    for label in labels:
        g=e[e.label==label];a=g.groupby('root_id')[fields].sum().reindex(b.ids,fill_value=0)
        for field in fields:column[(label,field)]=len(arrays);arrays.append(a[field].to_numpy())
    a=np.stack(arrays,axis=1);sums=a.sum(axis=0)
    transforms={k:b.apply(a,k) for k in ['hierarchical','base_only']}
    context=dict(phase=phase,condition=condition,view=view,stratum=stratum,resampling_plan=b.key)
    for label in labels:
        g=e[e.label==label];app=g.applicable.sum();valid=g.valid_output.sum()
        counts=dict(base_clusters=g.root_id.nunique(),event_conditions=len(g),applicable_equivalent=float(app),
            na_equivalent=float(len(g)-app),success_equivalent=float(g.online_success.sum()),
            valid_output_equivalent=float(valid),raw_calls=int(g.seed_calls.sum()),
            count_note='Search seeds averaged within event; fractional numerators are equivalent event counts, not integer Bernoulli counts')
        for metric,(num,den) in METRICS.items():
            ni=column[(label,num)];di=column[(label,den)];p=float(ratio(sums[ni],sums[di]));point[(label,metric)]=p
            for mode,trans in transforms.items():
                v=ratio(trans[:,ni],trans[:,di]);repvalues[(label,metric,mode)]=v
                key=f'method::{label}::{metric}::{mode}';reps[key]=v.astype(np.float32)
                stats.append(context|counts|dict(label=label,metric=metric,estimate=p,bootstrap=mode,**interval(v)))
    for left,right in pairs(phase,labels):
        for metric in EFFECT_METRICS:
            for mode in transforms:
                v=repvalues[left,metric,mode]-repvalues[right,metric,mode]
                reps[f'effect::{left}::{right}::{metric}::{mode}']=v.astype(np.float32)
                effects.append(context|dict(left=left,right=right,metric=metric,estimate=point[left,metric]-point[right,metric],bootstrap=mode,**interval(v)))
        join=['base_id','scenario','layer','kind','FR','q']
        j=e[e.label==left].merge(e[e.label==right],on=join,suffixes=('_a','_b'),validate='one_to_one')
        j=j[(j.valid_output_a==1)&(j.valid_output_b==1)]
        for metric in ['U_raw','N_drop','M_all']:
            g=pd.DataFrame({'root_id':j.root_id_a,'num':j[metric+'_a']-j[metric+'_b'],'den':1.})
            agg=g.groupby('root_id')[['num','den']].sum().reindex(b.ids,fill_value=0)
            pt=float(ratio(agg.num.sum(),agg.den.sum()))
            for mode in transforms:
                vv=b.apply(agg.to_numpy(),mode);v=ratio(vv[:,0],vv[:,1])
                reps[f'shared::{left}::{right}::{metric}::{mode}']=v.astype(np.float32)
                effects.append(context|dict(left=left,right=right,metric='all_seeds_both_valid_'+metric,estimate=pt,
                    paired_valid_events=len(j),paired_valid_clusters=j.root_id_a.nunique(),bootstrap=mode,**interval(v)))
        if right=='Minimal-Repair':
            j=j[j.U_raw_b>0]
            g=pd.DataFrame({'root_id':j.root_id_a,'num':(j.U_raw_a-j.U_raw_b)/j.U_raw_b,'den':1.})
            agg=g.groupby('root_id')[['num','den']].sum().reindex(b.ids,fill_value=0)
            for mode in transforms:
                vv=b.apply(agg.to_numpy(),mode);v=ratio(vv[:,0],vv[:,1])
                reps[f'normalized::{left}::{right}::{mode}']=v.astype(np.float32)
                effects.append(context|dict(left=left,right=right,metric='both_valid_positive_minimal_relative_gain',estimate=float(ratio(agg.num.sum(),agg.den.sum())),
                    paired_valid_events=len(j),paired_valid_clusters=j.root_id_a.nunique(),bootstrap=mode,**interval(v)))
    key=hashlib.sha256((phase+condition+view+stratum).encode()).hexdigest()[:20]
    path=OUT/'replicates'/phase/(key+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,**reps)
    save(path.with_suffix('.json'),context|dict(repetitions=REPS,columns=list(reps),storage='float32, intervals computed in float64',sha256=sha(path)))
    return stats,effects

def trajectories():
    e=pd.read_csv(P5/'tables/continuous_trajectories.csv');e['root_id']=e.base_id;e['label']=e.method
    b=bootstrap(e.base_id.unique());rows=[];effects=[];rep={}
    metrics=['delivered_utility','completed_tasks','online_success_events','failures','failure_to_success_recoveries',
        'cumulative_active_drops','cumulative_movement','expired_unserved_tasks','unserved_with_individually_feasible_window','unserved_without_any_individual_window']
    for mode in ['hierarchical','base_only']:
        values={}
        for label,g in e.groupby('label'):
            a=g.set_index('base_id')[metrics].reindex(b.ids);v=b.apply(a.to_numpy(),mode)/len(b.ids)
            for i,m in enumerate(metrics):
                values[label,m]=v[:,i];rep[f'{label}::{m}::{mode}']=v[:,i].astype(np.float32)
                rows.append(dict(label=label,metric=m,bootstrap=mode,estimate=a[m].mean(),trajectories=len(a),**interval(v[:,i])))
        for left,right in pairs('continuous',e.label.unique()):
            for m in metrics:
                v=values[left,m]-values[right,m];rep[f'effect::{left}::{right}::{m}::{mode}']=v.astype(np.float32)
                effects.append(dict(left=left,right=right,metric=m,bootstrap=mode,estimate=float(e[e.label==left][m].mean()-e[e.label==right][m].mean()),**interval(v)))
    csv('trajectory_statistics.csv',pd.DataFrame(rows));csv('trajectory_effects.csv',pd.DataFrame(effects))
    path=OUT/'replicates/trajectories.npz';np.savez_compressed(path,**rep)
    save(path.with_suffix('.json'),dict(plan=b.key,unit='Whole 10-event trajectory; realized state paths differ by method',repetitions=REPS,sha256=sha(path)))

def main():
    inventory=[]
    selected=os.environ.get('P6_REBUILD_PHASE')
    for phase in ['P4']+[p for p in PHASES if p not in ['calibration','continuous']]:
        if selected and phase!=selected:continue
        if (OUT/'tables'/(phase+'_statistics.csv')).exists() and not selected:continue
        e=pd.read_csv(OUT/'tables'/(phase+'_events.csv.gz'),keep_default_na=False)
        stats=[];effects=[]
        conditions=['factor','value','variant'] if phase in ['single_factor','windows','anomalies'] else []
        groups=e.groupby(conditions,dropna=False) if conditions else [('all',e)]
        for ck,c in groups:
            condition='|'.join(str(x) for x in ck) if isinstance(ck,tuple) else str(ck)
            b=bootstrap(c.root_id.unique())
            for view,stratum,g in masks(c,phase):
                s,d=infer_view(g,b,phase,condition,view,stratum);stats+=s;effects+=d
            print(json.dumps(dict(inferred=phase,condition=condition,statistics=len(stats),effects=len(effects))),flush=True)
        csv(phase+'_statistics.csv',pd.DataFrame(stats));csv(phase+'_effects.csv',pd.DataFrame(effects))
    trajectories()
    for phase in ['P4']+[p for p in PHASES if p not in ['calibration','continuous']]:
        d=pd.read_csv(OUT/'tables'/(phase+'_effects.csv'))
        inventory.extend(d[['phase','left','right']].drop_duplicates().to_dict('records'))
    save(OUT/'comparison_inventory.json',dict(comparisons=inventory,p_values=False,intervals='Marginal percentile 95%, not simultaneous; no significance selection',
        shared_valid='Both methods valid on every seed of event; conservative event-level intersection, explicit counts',repetitions=REPS,seed=SEED))
    save(OUT/'statistics_COMPLETE.json',dict(passed=True,repetitions=REPS,seed=SEED,plans=len(list((OUT/'resampling').glob('*.npz'))),replicate_files=len(list((OUT/'replicates').rglob('*.npz')))))

if __name__=='__main__':main()
