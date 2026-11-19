"""Freeze P6 consumed evidence and bootstrap unit metadata without editing old runs."""
import subprocess,platform,importlib.metadata
import numpy as np
import pandas as pd
from p6_common import *

def events(df):
    for k in ['FR','q','value','budget_ms']:df[k]=pd.to_numeric(df[k],errors='coerce')
    dims=['base_id','root_id','layer','scenario','kind','FR','q','label','factor','value','variant','budget_ms']
    assert not df.duplicated(dims+['seed']).any(),'Duplicate method/event/seed'
    for key,g in df.groupby(dims,dropna=False,sort=False):
        assert len(g) in [1,5],(key,len(g))
        if len(g)==5:assert set(g.seed)=={11,23,47,89,131},key
    for k in ['U_raw','N_drop','N_add','N_sym','M_all','M_edit','N_forced']:
        df['accepted_'+k]=df[k]*df.valid_output
    df['urgent']=df.kind.eq('urgent_insertion').astype(float)
    df['online_urgent']=df.online_success*df.urgent
    df['applicable_urgent']=df.applicable*df.urgent
    numeric=['applicable','strict_feasible','service_success','online_success','valid_output','U_exec','timeout','total_ms',
             'U_raw','N_drop','N_add','N_sym','M_all','M_edit','N_forced','urgent','online_urgent','applicable_urgent']
    numeric+=['accepted_'+k for k in ['U_raw','N_drop','N_add','N_sym','M_all','M_edit','N_forced']]
    for k in numeric:df[k]=pd.to_numeric(df[k],errors='raise').astype(float)
    g=df.groupby(dims,dropna=False,sort=True)
    e=g[numeric].mean().reset_index();e['seed_calls']=g.size().to_numpy()
    assert np.allclose(e.U_exec,e.accepted_U_raw)
    return e

def p4():
    df=pd.read_csv(P4/'per_event_results.csv',keep_default_na=False)
    for k in ['applicable','strict_feasible','service_success','online_success','valid_output']:
        df[k]=df[k].map({True:1,False:0,'True':1,'False':0})
        assert df[k].notna().all()
    df['root_id']=df.base_id;df['label']=df.method;df['seed']=df.search_seed
    df['factor']='';df['value']=np.nan;df['variant']='';df['budget_ms']=50.
    df['timeout']=(df.total_ms>50).astype(float);df['N_forced']=0.
    return df

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent,text=True).strip()
    parent='d940b9afc36a7451d92f49fe6929493b1d3a2602'
    assert current==parent or os.environ.get('P6_ALLOW_DELIVERED')=='1',current
    tree={}
    for line in subprocess.check_output(['git','ls-tree','-rz',parent],cwd=ROOT.parent).decode().split('\0'):
        if line:
            a,name=line.split('\t',1);mode,kind,oid=a.split()
            if kind=='blob':tree[name]=oid
    save(OUT/'historical_git_blobs.json',dict(parent_commit=parent,files=tree))
    inputs=[SOURCE/'protocol/complete_experimental_plan.v1.md',SOURCE/'protocol/P4_STATISTICS_V1.md',P4/'data/manifest.json',P4/'per_event_results.csv',P4/'acceptance_manifest.json',P4/'final_audit.json',P4/'cluster_bootstrap.json',P4/'timing_table.csv',P4/'main_table.csv',P5/'acceptance_manifest.json',P5/'final_acceptance.json',P5/'acceptance_details.json',P5/'subsets.json',P5/'summary_receipt.json']
    inputs+=list((P5/'tables').glob('*'))
    inputs += [SOURCE/'reports'/name for name in ['P0_REPORT.md','P1_REPORT.md','P2_REPORT.md','P3_REPORT.md']]
    inputs += [SOURCE/'reports/p3r/P3R-20261112/P3R_REPORT.md',P4/'P4_REPORT.md',P5/'P5_REPORT.md',P4/'test_freeze.json']
    inputs += list((P5/'prior_stage_review').glob('*.md'))
    inputs += list(P5.glob('*/source_freeze.json'))
    inputs+=[p for p in (SOURCE/'reports/p2/P2-20261105T114327Z').glob('*') if p.suffix in ['.json','.csv']]
    save(OUT/'source_manifest.json',dict(parent_commit=parent,files={p.relative_to(SOURCE).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in inputs if p.is_file()},
         policy='Source bytes remain untouched; P6 outputs are additional analyses, not replacements. Raw shard and receipt hashes independently checked by audit_stage6_raw.py.'))
    save(OUT/'unit_metadata.json',metadata())
    environment=dict(python=platform.python_version(),platform=platform.platform(),packages={n:importlib.metadata.version(n) for n in ['numpy','pandas','matplotlib','scipy','pytest']},
        analysis_only=True,performance_experiments_rerun=False,threads={k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']})
    save(OUT/'environment.json',environment)
    counts={}
    for name in ['P4']+PHASES:
        df=p4() if name=='P4' else pd.read_csv(P5/'tables'/(name+'_per_call.csv.gz'),keep_default_na=False)
        if name!='P4':
            for k in ['factor','variant']:df[k]=df[k].fillna('')
        e=events(df)
        csv(name+'_events.csv.gz',e)
        counts[name]=dict(raw_calls=len(df),event_method_conditions=len(e),root_clusters=e.root_id.nunique())
        print(json.dumps(dict(prepared=name,**counts[name])),flush=True)
    save(OUT/'prepared.json',dict(phases=counts,all_search_seed_sets_complete=True,scope='Published P4/P5 only; cancelled P4-M/P5-M excluded'))

if __name__=='__main__':main()
