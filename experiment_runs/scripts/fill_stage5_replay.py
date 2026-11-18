"""Replay a fixed disjoint list missed by an earlier directory scan.

Run only after every original watcher has moved beyond this phase.
No performance methods are called. The regular final verifier still checks all.
"""
import argparse
from p5_common import *
from verify_stage5_evidence import verify


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,required=True)
    p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    assert (OUT/'pipeline/COMPLETE.json').exists()
    manifest=load(OUT/'audit/fill_manifest.json');rows=manifest['rows'][args.worker::args.workers]
    for i,row in enumerate(rows):
        path=ROOT/row['path'];assert sha(path)==row['sha256']
        verify(row['phase'],path)
        if i%5==0:print(json.dumps(dict(worker=args.worker,done=i+1,total=len(rows))),flush=True)
    save(OUT/'audit'/f'fill-worker{args.worker}.json',dict(passed=True,rows=len(rows),manifest_sha256=sha(OUT/'audit/fill_manifest.json')))


if __name__=='__main__':main()
