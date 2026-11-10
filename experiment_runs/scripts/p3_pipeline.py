"""Sequential single-core P3 continuation. Stops on any failed required step."""
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];run=ROOT/'reports/p3/P3-20261110'
steps=[('labels','p3_experiment.py','labels'),('train_et','train_p3_et.py'),
       ('grid','p3_validation.py','grid'),('summarize_grid','summarize_p3.py','grid'),
       ('rules','p3_validation.py','rules'),('summarize_rules','summarize_p3.py','rules'),
       ('et','p3_validation.py','et'),('summarize_et','summarize_p3.py','et'),
       ('search','p3_search_validation.py'),('summarize_search','summarize_p3.py','search'),
       ('calibration','calibrate_p3_et.py')]
log=run/'pipeline';log.mkdir(exist_ok=True)
if '--wait-labels' in sys.argv:
    while not (run/'labels/COMPLETE.json').exists():
        print('WAIT initial labels',len(list((run/'labels').glob('*.receipt.json'))),'/4000',flush=True)
        time.sleep(30)
for name,script,*args in steps:
    receipt=log/(name+'.complete.json')
    if receipt.exists():continue
    # The separately running initial labels job must have finished first.
    if name=='labels' and (run/'labels/COMPLETE.json').exists():
        assert json.loads((run/'labels/COMPLETE.json').read_text())['full'];continue
    if name=='train_et' and (run/'models/index.json').exists():continue
    if name=='summarize_rules' and (run/'selection_fixed_rule.json').exists():continue
    print('START',name,datetime.now(timezone.utc).isoformat(),flush=True)
    with (log/(name+'.log')).open('a',encoding='utf-8') as output:
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*args],stdout=output,stderr=subprocess.STDOUT)
    if result.returncode:
        print('FAILED',name,'exit',result.returncode,'see',str(log/(name+'.log')),flush=True)
        sys.exit(result.returncode)
    receipt.write_text(json.dumps(dict(step=name,completed_at_utc=datetime.now(timezone.utc).isoformat()))+'\n')
    print('DONE',name,flush=True)
print('All P3 computation steps complete; independent final audit/report still required',flush=True)
