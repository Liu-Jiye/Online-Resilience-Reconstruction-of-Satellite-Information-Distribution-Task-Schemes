"""P4 paths and immutable evidence helpers."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
P3=ROOT/'reports/p3/P3-20261110'
P3R=ROOT/'reports/p3r/P3R-20261112'
OUT=ROOT/'reports/p4/P4-20261117'
SEEDS=[11,23,47,89,131]
METHODS=['Minimal-Repair','Frozen-Greedy','Fixed-PALR','Validation-Best-Fixed','Rule-PALR','PUCT-ISL','ALNS-ISL','CP-SAT-50ms']
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');t.replace(p)
def sources():
    paths=sorted((ROOT/'src/isl').glob('*.py'))+sorted((ROOT/'src/isl/p3r').glob('*.py'))+sorted((ROOT/'src/isl/p4').glob('*.py'))+sorted((ROOT/'scripts').glob('*p4*.py'))
    paths += [ROOT/'protocol/P4_EXECUTION_V1.md',P3/'frozen_parameters.json',P3/'search_training_statistics.json',P3R/'selected_controllers.json']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}
