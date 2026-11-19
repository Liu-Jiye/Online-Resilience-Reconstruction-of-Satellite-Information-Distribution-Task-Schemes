"""Verify accepted P6 bytes in index and GitHub subtree without medium leftovers."""
import argparse,hashlib,subprocess,time
from p6_common import *

SLUG='Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT.parent).decode().strip()
def api(endpoint):
    for attempt in range(3):
        r=subprocess.run(['gh','api','--cache','1h',endpoint],cwd=ROOT.parent,capture_output=True,text=True,encoding='utf-8')
        if r.returncode==0:return json.loads(r.stdout)
        if attempt==2:raise RuntimeError(r.stderr)
        time.sleep(2)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--remote',action='store_true');parser.add_argument('--receipt',type=Path,required=True);args=parser.parse_args()
    manifest=load(OUT/'acceptance_manifest.json');accepted={OUT/name:e['sha256'] for name,e in manifest['files'].items()}
    accepted[OUT/'acceptance_manifest.json']=sha(OUT/'acceptance_manifest.json')
    accepted.update({ROOT/name:digest for name,digest in manifest['source_code'].items()})
    index={}
    for line in git('ls-files','--stage','-z').split('\0'):
        if line:
            info,name=line.split('\t',1);index[name]=info.split()[1]
    for path,digest in accepted.items():
        assert sha(path)==digest,path
        blob=hashlib.sha1(f'blob {path.stat().st_size}\0'.encode())
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):blob.update(block)
        oid=blob.hexdigest()
        assert index.get(path.relative_to(ROOT.parent).as_posix())==oid,('Accepted bytes differ from Git index',str(path))
    staged=git('diff','--cached','--name-only','-z').split('\0')
    assert all(not p or (p.startswith('experiment_runs/') and 'P4-M' not in p and 'P5-M' not in p and '/medium' not in p and 'MEDIUM_' not in p) for p in staged)
    result=dict(passed=True,accepted_files_exact_git_bytes=len(accepted),medium_artifacts_included=False)
    if args.remote:
        commit=git('rev-parse','HEAD');head=git('ls-remote','origin','refs/heads/main').split()[0];assert head==commit
        native=api(f'repos/{SLUG}/git/commits/{commit}');assert native['sha']==commit
        assert native['tree']['sha']==git('rev-parse',commit+'^{tree}')
        prefix=OUT.relative_to(ROOT.parent).as_posix();tree=git('rev-parse',commit+':'+prefix)
        remote=api(f'repos/{SLUG}/git/trees/{tree}?recursive=1');assert not remote.get('truncated') and remote['sha']==tree
        remote_blobs={r['path']:r['sha'] for r in remote['tree'] if r['type']=='blob'}
        local={}
        for line in git('ls-tree','-rz',commit+':'+prefix).split('\0'):
            if line:
                info,name=line.split('\t',1);local[name]=info.split()[2]
        assert remote_blobs==local
        assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
        result.update(commit=commit,remote_main=head,remote_root_tree_sha=native['tree']['sha'],p6_tree_sha=tree,
            p6_remote_blobs_matched=len(local),tracked_worktree_clean=True,
            local_untracked_medium_remnants='Excluded; deletion rejected by automatic approval policy',
            url=f'https://github.com/{SLUG}/commit/{commit}',receipt_scope='This receipt verifies the core scientific commit; receipt/export archival may appear in a subsequent delivery-only commit.')
    save(args.receipt,result);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
