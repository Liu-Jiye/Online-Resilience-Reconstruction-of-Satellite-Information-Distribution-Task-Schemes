"""Paired hierarchical cluster bootstrap; no event-level pseudoreplication."""
import hashlib
import numpy as np
from p6_common import *

def plans(ids,meta,reps=REPS,seed=SEED):
    ids=sorted(ids);n=len(ids);layers=sorted({meta[i]['layer'] for i in ids})
    bylayer={l:np.array([j for j,i in enumerate(ids) if meta[i]['layer']==l]) for l in layers}
    groups={l:{g:np.array([j for j in bylayer[l] if meta[ids[j]]['group']==g]) for g in sorted({meta[ids[j]]['group'] for j in bylayer[l]})} for l in layers if l!='D1'}
    rng=np.random.Generator(np.random.PCG64(seed));base=np.zeros((reps,n),dtype=np.uint16);hier=np.zeros_like(base)
    for k in range(reps):
        sampled={l:rng.choice(ix,len(ix),replace=True) for l,ix in bylayer.items()}
        for l in layers:base[k]+=np.bincount(sampled[l],minlength=n).astype(np.uint16)
        for l,gs in groups.items():
            names=list(gs);selected=rng.integers(0,len(names),len(names))
            sampled[l]=np.concatenate([rng.choice(gs[names[g]],len(gs[names[g]]),replace=True) for g in selected])
        for l in layers:hier[k]+=np.bincount(sampled[l],minlength=n).astype(np.uint16)
    return ids,bylayer,groups,base,hier

def normalize(counts,bylayer):
    w=counts.astype(float)
    for indices in bylayer.values():w[:,indices]*=len(indices)/w[:,indices].sum(axis=1)[:,None]
    return w

def interval(values):
    a=np.asarray(values);good=a[np.isfinite(a)]
    lo,hi=np.percentile(good,[2.5,97.5]) if len(good) else (None,None)
    return dict(ci95_low=None if lo is None else float(lo),ci95_high=None if hi is None else float(hi),defined_replicates=len(good),undefined_replicates=len(a)-len(good))

def ratio(num,den):
    return np.divide(num,den,out=np.full(np.broadcast_shapes(np.shape(num),np.shape(den)),np.nan,dtype=float),where=np.asarray(den)>0)

class Bootstrap:
    def __init__(self,ids,meta,reps=REPS):
        self.ids,self.layers,self.groups,b,h=plans(ids,meta,reps)
        self.base=normalize(b,self.layers);self.hier=normalize(h,self.layers)
        self.key=hashlib.sha256('\n'.join(self.ids).encode()).hexdigest()[:16]
        self.path=OUT/'resampling'/(self.key+'.npz');self.path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(self.path,base_counts=b,hierarchical_counts=h,ids=np.array(self.ids))
        save(self.path.with_suffix('.json'),dict(repetitions=reps,seed=SEED,ids=self.ids,
             layer_counts={l:len(ix) for l,ix in self.layers.items()},orbit_groups={l:{g:len(ix) for g,ix in gs.items()} for l,gs in self.groups.items()},
             original_layer_weights_preserved=True,counts_file_sha256=sha(self.path)))
    def apply(self,array,kind='hierarchical'):
        weights=self.hier if kind=='hierarchical' else self.base
        active=np.any(array!=0,axis=1) if array.ndim>1 else array!=0
        return weights[:,active]@array[active]
