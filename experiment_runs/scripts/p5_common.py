"""P5 immutable paths, deterministic sample selection and atomic receipts."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
P3=ROOT/'reports/p3/P3-20261110'
P4=ROOT/'reports/p4/P4-20261117'
OUT=ROOT/'reports/p5/P5-20261118'
SEEDS=[11,23,47,89,131]
LIGHT=['Minimal-Repair','Fixed-PALR','Validation-Best-Fixed','Rule-PALR']

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8');t.replace(p)
def sealed(p,v):
    if p.exists():assert load(p)==v,('immutable receipt differs',str(p))
    else:save(p,v)
def base_data(ident,stage=P4,load_name='default'):
    with zipfile.ZipFile(stage/'data'/(ident+'.zip')) as z:return json.loads(z.read(load_name+'.json'))
def source_hashes():
    paths=list((ROOT/'src/isl').rglob('*.py'))+list((ROOT/'scripts').glob('*p5*.py'))+[ROOT/'protocol/P5_EXECUTION_V1.md']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)}
