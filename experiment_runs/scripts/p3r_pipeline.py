"""Continue the already authorized P3-R steps, stop on errors, never retune."""
import json,os,platform,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/p3r/P3R-20261112'
def main():
    assert platform.system()=='Linux'
    env=dict(system=platform.uname()._asdict(),python=sys.version,cpu_affinity=sorted(os.sched_getaffinity(0)),
         started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         pip_freeze=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
         image='satellite-p3:20261110-locked',image_id='sha256:c465af02e860b05f063ca84b138e1cca72c235574b402937e6fb2eaf5d6ec728')
    (OUT/'revision_environment.json').write_text(json.dumps(env,indent=2)+'\n')
    steps=[('controller_gate','p3r_controller_gate.py'),('validation','p3r_validate.py'),('finalize','finalize_p3r.py')]
    logs=OUT/'pipeline';logs.mkdir(exist_ok=True)
    for name,script in steps:
        receipt=logs/(name+'.complete.json')
        if receipt.exists():continue
        print('START',name,flush=True)
        with (logs/(name+'.log')).open('a') as f:
            p=subprocess.run([sys.executable,str(ROOT/'scripts'/script)],stdout=f,stderr=subprocess.STDOUT)
        if p.returncode:print('FAILED',name,p.returncode,flush=True);sys.exit(p.returncode)
        receipt.write_text(json.dumps(dict(step=name,completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))+'\n')
        print('DONE',name,flush=True)
    print('P3-R finished; inspect final audit and report',flush=True)
if __name__=='__main__':main()
