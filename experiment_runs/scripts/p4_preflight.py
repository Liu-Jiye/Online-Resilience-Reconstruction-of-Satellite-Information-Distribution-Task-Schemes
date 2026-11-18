"""Training-only adapter acceptance and immutable historical stage audit."""
import json,os,platform,subprocess,time,zipfile
from p4_common import *
from isl.models import case_from_dict,frozen_count
from isl.p3r.repair_runtime import run_method
from isl.p3r.control_timed import controlled
from isl.p3r.search import run_puct,run_alns
from isl.p4.online import run_cp,enforce_wall
from train_p3r import replay

def main():
    assert platform.system()=='Linux' and platform.python_version().startswith('3.11.') and sorted(os.sched_getaffinity(0))==[0]
    envvars={k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')};assert set(envvars.values())=={'1'}
    save(OUT/'environment.json',dict(python=platform.python_version(),platform=platform.platform(),affinity=sorted(os.sched_getaffinity(0)),thread_environment=envvars,cpuinfo=Path('/proc/cpuinfo').read_text(),meminfo=Path('/proc/meminfo').read_text(),os_release=Path('/etc/os-release').read_text(),pip_freeze=subprocess.check_output(['python','-m','pip','freeze'],text=True),image='sha256:c465af02e860b05f063ca84b138e1cca72c235574b402937e6fb2eaf5d6ec728'))
    integrity=load(OUT/'historical_integrity.json')
    assert integrity['all_unchanged']
    assert integrity['P3_manifest_sha256']==sha(P3/'acceptance_manifest.json')
    assert integrity['P3R_manifest_sha256']==sha(P3R/'acceptance_manifest.json')
    cfg=load(P3/'frozen_parameters.json')['parameters']['default'];stats=load(P3/'search_training_statistics.json')
    rows=load(P3/'data/manifest.json')['instances'];checks=[]
    for layer in ('D1','D2-S','D2-O'):
        row=next(r for r in rows if r['split']=='train' and r['layer']==layer)
        with zipfile.ZipFile(P3/'data'/(row['id']+'.zip')) as z:d=json.loads(z.read('default.json'))
        for e in d['events']:
            case=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
            for m in METHODS:
                for seed in (SEEDS if m in ('PUCT-ISL','ALNS-ISL') else [11]):
                    began=time.perf_counter_ns()
                    if m in ('Minimal-Repair','Frozen-Greedy','Fixed-PALR'):r=run_method(case,m)
                    elif m=='Validation-Best-Fixed':r=run_method(case,**cfg['fixed'])
                    elif m=='Rule-PALR':r=controlled(case,cfg['rule'])
                    elif m=='PUCT-ISL':r=run_puct(case,temperature=.5,density_mean=stats['mean'],density_std=stats['std'],seed=seed)
                    elif m=='ALNS-ISL':r=run_alns(case,seed=seed)
                    else:r=run_cp(case,seed=seed)
                    r=enforce_wall(r,time.perf_counter_ns()-began);replay(case,r)
                    assert r['admissions_cumulative']<=5
                    if r['total_ns']>50_000_000:assert not r['metrics']['online_success'] and r['metrics']['U_exec']==0
                    checks.append(dict(layer=layer,scenario=e['scenario_index'],method=m,seed=seed,status=r['status'],total_ns=r['total_ns']))
        print('P4 training preflight passed',layer,flush=True)
    save(OUT/'training_preflight.json',dict(passed=True,checks=checks,test_calls=0,protocol='all outcomes retained; no performance-based tuning'))
if __name__=='__main__':main()
