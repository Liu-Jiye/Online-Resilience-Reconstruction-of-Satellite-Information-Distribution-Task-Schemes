"""Capture host scheduling receipt and current locked-image runtime versions."""
import subprocess,platform,importlib.metadata
from p5_common import *

def main():
    containers={}
    names=subprocess.check_output(['docker','ps','-a','--filter','name=satellite-p5','--format','{{.Names}}'],text=True).splitlines()
    for name in sorted(names):
        r=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
        containers[name]=dict(image=r['Image'],cpuset=r['HostConfig']['CpusetCpus'],command=r['Config']['Cmd'],started_at=r['State']['StartedAt'],
            finished_at=r['State']['FinishedAt'],status=r['State']['Status'],exit_code=r['State']['ExitCode'],oom_killed=r['State']['OOMKilled'])
    code="import json,os,platform,importlib.metadata as m;print(json.dumps(dict(python=platform.python_version(),platform=platform.platform(),packages={p:m.version(p) for p in ['numpy','ortools','sgp4','skyfield','alns','matplotlib','pandas','scipy']},threads={k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','PYTHONHASHSEED']},cpu_model=next(x for x in open('/proc/cpuinfo') if x.startswith('model name')).strip())))"
    runtime=json.loads(subprocess.check_output(['docker','run','--rm','--cpuset-cpus','2','satellite-p3:20261110-locked','python','-c',code],text=True))
    save(OUT/'environment.json',dict(containers=containers,runtime=runtime,
        timing_scope='Full Python execute dispatch through return, includes feature extraction, search, validation, metrics and return object; excludes disk, encoding, independent audit and initial reference creation',
        isolation='Formal methods serialized on logical CPU0. Input generation/offline replay use other logical CPUs; exact cpusets and exit states are listed above. WSL/Docker and host scheduling may still cause jitter; no hard-real-time guarantee.',
        offline_audit_restart='Initial single offline replay container was stopped (exit137) and replaced by three partitioned workers on CPUs2/4/6. Sealed raw performance shards were retained; final replay checks all shards regardless of worker.',
        delivery_verification_runtime=dict(python=platform.python_version(),platform=platform.platform(),pandas=importlib.metadata.version('pandas'),
            scope='Host-only final file/hash/denominator and Git-byte checks; no model inference, planning or performance rerun. All formal calls and physical replays used the locked Linux image.',
            stopped_container='satellite-p5-finalizer was stopped during historical file hashing to avoid Docker bind-mount small-file overhead; the same acceptance script was then run on the host. This was not a formal experiment or physical replay failure.'),
        parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent,text=True).strip()))

if __name__=='__main__':main()
