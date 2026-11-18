"""Serialize remaining CPU0 formal runs after the already sealed ablation batch."""
import subprocess,os,time,sys,platform
from p5_common import *

def main():
    assert platform.system()=='Linux' and sorted(os.sched_getaffinity(0))==[0]
    for prerequisite in ('ablations/COMPLETE.json','inputs/COMPLETE.json','semantic_continuous_v2/COMPLETE.json'):
        print('waiting for '+prerequisite,flush=True)
        while not (OUT/prerequisite).exists():time.sleep(10)
    steps=[('continuous_training_preflight','run_p5_continuous_v2.py',{'P5_CONTINUOUS_PREFLIGHT':'1'}),
        ('searches','run_p5_searches.py',{}),('special','run_p5_special.py',{}),
        ('references','run_p5_references.py',{}),('transfer','run_p5_transfer.py',{}),
        ('continuous','run_p5_continuous_v2.py',{})]
    statuses=[]
    for name,script,env in steps:
        start=time.time();path=OUT/'pipeline'/(name+'.log');path.parent.mkdir(parents=True,exist_ok=True)
        print('starting '+name,flush=True)
        with path.open('a') as f:
            rc=subprocess.run([sys.executable,'-u','scripts/'+script],stdout=f,stderr=subprocess.STDOUT,env={**os.environ,**env}).returncode
        statuses.append(dict(step=name,script=script,exit_code=rc,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(start)),elapsed_s=time.time()-start))
        save(OUT/'pipeline/status.json',dict(steps=statuses,complete=False))
        print(json.dumps(statuses[-1]),flush=True)
        if rc:raise SystemExit(rc)
    save(OUT/'pipeline/COMPLETE.json',dict(steps=statuses,complete=True))

if __name__=='__main__':main()
