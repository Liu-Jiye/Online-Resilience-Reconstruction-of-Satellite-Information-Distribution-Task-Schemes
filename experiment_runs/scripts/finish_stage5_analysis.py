"""Queue only P5 replay/analysis after all serialized formal calls and audit workers."""
import os,time,subprocess,sys
from p5_common import *

def main():
    print('Waiting for all P5 formal phases and three offline replay workers',flush=True)
    while not (OUT/'pipeline/COMPLETE.json').exists():time.sleep(10)
    for worker in range(3):
        while not (OUT/'audit'/f'progress-worker{worker}.json').exists():time.sleep(10)
        assert load(OUT/'audit'/f'progress-worker{worker}.json')['pipeline_complete']
    if (OUT/'audit/fill_manifest.json').exists():
        for worker in range(4):
            while not (OUT/'audit'/f'fill-worker{worker}.json').exists():time.sleep(10)
            assert load(OUT/'audit'/f'fill-worker{worker}.json')['passed']
    phases=['verify_stage5_evidence.py','summarize_stage5.py','plot_stage5.py','write_stage5_report.py']
    statuses=[]
    for script in phases:
        path=OUT/'analysis'/script.replace('.py','.log');path.parent.mkdir(parents=True,exist_ok=True)
        start=time.time();print('Starting '+script,flush=True)
        with path.open('a') as f:
            rc=subprocess.run([sys.executable,'-u','scripts/'+script],stdout=f,stderr=subprocess.STDOUT,
                env={**os.environ,'P5_AUDIT_WATCH':'0','P5_AUDIT_WORKER':'0','P5_AUDIT_WORKERS':'1','P5_AUDIT_FINAL':'1'}).returncode
        statuses.append(dict(script=script,exit_code=rc,elapsed_s=time.time()-start));save(OUT/'analysis/status.json',dict(steps=statuses))
        if rc:raise SystemExit(rc)
    save(OUT/'analysis/COMPLETE.json',dict(steps=statuses,formal_pipeline_complete=True,P6_started=False))
    print('P5 analysis complete, awaiting final delivery verification and Git push',flush=True)

if __name__=='__main__':main()
