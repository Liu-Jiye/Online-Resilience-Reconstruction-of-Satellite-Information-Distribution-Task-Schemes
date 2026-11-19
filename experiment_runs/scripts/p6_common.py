"""P6 isolated, read-only analysis of previously published experiment evidence."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ.get('P6_SOURCE',str(ROOT)))
OUT=Path(os.environ.get('P6_OUT',str(ROOT/'reports/p6/P6-20261118')))
P4=SOURCE/'reports/p4/P4-20261117'
P5=SOURCE/'reports/p5/P5-20261118'
sys.path.insert(0,str(SOURCE/'src'))
PHASES=['ablations','calibration','mechanisms','simulations','upgrades','single_factor','windows','anomalies','references','transfer','continuous']
REPS=10000
SEED=20261020
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def metadata():
    return {r['id']:dict(layer=r['layer'],group=r['geometry'].get('group','D1')) for r in load(P4/'data/manifest.json')['instances']}
def csv(name,df):
    p=OUT/'tables'/name;p.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(p,index=False,encoding='utf-8',compression='infer')
