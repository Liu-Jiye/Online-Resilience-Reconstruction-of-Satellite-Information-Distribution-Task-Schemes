"""Host-side byte hashing avoids Docker bind-mount metadata overhead; no timing."""
from p4_common import *
def main():
    n=nr=0
    for p,h in load(P3/'acceptance_manifest.json')['file_sha256'].items():
        assert sha(ROOT.parent/p)==h,p;n+=1
        if n%1000==0:print('P3 checked',n,flush=True)
    for p,h in load(P3R/'acceptance_manifest.json')['files'].items():
        assert sha(ROOT/p)==h,p;nr+=1
        if nr%1000==0:print('P3R checked',nr,flush=True)
    save(OUT/'historical_integrity.json',dict(P3_files=n,P3R_files=nr,all_unchanged=True,
         P3_manifest_sha256=sha(P3/'acceptance_manifest.json'),P3R_manifest_sha256=sha(P3R/'acceptance_manifest.json'),
         boundary='host byte hashing only, no algorithm timing'))
if __name__=='__main__':main()
