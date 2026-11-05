"""Read-only P2-C verification; optional full replay writes only a temp copy."""
import argparse
from pathlib import Path
import shutil
import tempfile
from p2c_study import ROOT,REPO,check_manifest,old_hashes,load,sha,audit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--replay',action='store_true');args=parser.parse_args()
    out=Path(args.folder).resolve();inputs=ROOT/'reports/p2/P2C-inputs-v1'
    check_manifest(inputs);check_manifest(out);old_hashes()
    assert load(out/'manifest.json')['input_manifest_sha256']==sha(inputs/'manifest.json')
    original=load(out/'independent_audit.json');assert original['passed'] and original['all_models_replayed']==1025
    acceptance=out/'acceptance_manifest.json'
    if acceptance.exists():
        for name,h in load(acceptance)['file_sha256'].items():assert sha(REPO/name)==h,name
    if args.replay:
        work=REPO.parent.resolve()
        with tempfile.TemporaryDirectory(prefix='p2c-reaudit-',dir=work) as temp:
            clone=Path(temp).resolve()
            assert clone.parent==work and clone.name.startswith('p2c-reaudit-')
            shutil.copytree(out,clone,dirs_exist_ok=True)
            (clone/'independent_audit.json').unlink()
            audit(clone)
            assert load(clone/'independent_audit.json')==original
    print('PASS P2-C hashes, frozen inputs, prior evidence and audit'+('; all 1025 models re-replayed' if args.replay else '; use --replay for full re-solve'))


if __name__=='__main__':main()
