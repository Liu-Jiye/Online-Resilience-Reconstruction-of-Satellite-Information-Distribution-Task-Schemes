"""Parallel read-only replay of independent single-factor shards, then exact merge."""
import subprocess
from collections import Counter
from p6_common import *

def main():
    processes=[];logs=[]
    directory=OUT/'raw_audit/single_factor';directory.mkdir(parents=True,exist_ok=True)
    for partition in range(4):
        log=(directory/f'partition-{partition}.log').open('w',encoding='utf-8');logs.append(log)
        command=[sys.executable,'-c',f"from audit_stage6_raw import audit; audit('single_factor',{partition},4)"]
        environment=dict(os.environ,PYTHONPATH=str(ROOT/'scripts'))
        processes.append(subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=environment))
    for partition,process in enumerate(processes):
        code=process.wait();assert code==0,(partition,code)
    for log in logs:log.close()
    counts=Counter();shards={};examples={}
    for partition in range(4):
        d=load(directory/f'COMPLETE.part-{partition}.json');assert d['passed']
        assert not set(shards)&set(d['raw_sha256'])
        shards.update(d['raw_sha256']);counts.update(d['counts'])
        for example in load(directory/f'examples.part-{partition}.json'):
            category=example['category']
            if category not in examples or example['source']<examples[category]['source']:examples[category]=example
    assert counts['calls']==99840 and len(shards)==2280
    assert len(list(directory.glob('*.csv.gz')))==2280
    save(directory/'COMPLETE.json',dict(passed=True,counts=dict(counts),raw_sha256=shards,
        partitions=4,partition_disjoint_and_complete=True,recheck_scope='All metrics/scoring, every unvalidated plan and first validated output per method/seed/shard; same checker and procedure as sequential phases'))
    save(directory/'examples.json',list(examples.values()))
    print(json.dumps(dict(passed=True,phase='single_factor',**dict(counts))),flush=True)

if __name__=='__main__':main()
