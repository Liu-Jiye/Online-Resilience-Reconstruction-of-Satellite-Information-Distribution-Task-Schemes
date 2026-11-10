"""Predeclared validation selection, one frozen choice per load."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
run=ROOT/'reports/p3/P3-20261110'


def summarize(mode):
    complete=json.loads((run/mode/'COMPLETE.json').read_text())
    assert complete['full'] and complete['base_count']==1000
    configs={};n=0
    for path in sorted((run/mode).glob('*.json.gz')):
        with gzip.open(path,'rt',encoding='utf-8') as f:
            for line in f:
                row=json.loads(line);m=row['result']['metrics'];n+=1
                setting=json.dumps(row['setting']);key=(row['load'],setting)
                if key not in configs:configs[key]=dict(cells=defaultdict(lambda:np.zeros(7)),times=[],count=0,timeouts=0,invalid=0,setting=row['setting'])
                config=configs[key];config['count']+=1;config['timeouts']+=row['result']['status']=='timeout'
                config['invalid']+=not m['strict_feasible']
                config['times'].append(row['result']['total_ns'])
                if not m['applicable']:continue
                cell=config['cells'][row['layer'],row['scenario']]
                cell+=np.asarray([1,int(m['online_success']),m['U_exec']/max(1,row['reference_utility']),m['N_drop'],m['N_add'],m['M_all'],int(m['valid_output'])])
    expected={'grid':600000,'rules':72000,'et':144000,'search':96000}[mode]
    assert n==expected,(mode,n)
    summaries=[]
    cfg=json.loads((ROOT/'configs/p3_v1.json').read_text())
    order=([ [w,b] for w in cfg['w'] for b in cfg['B']] if mode=='grid' else
           [r['name'] for r in cfg['rule_candidates']] if mode=='rules' else
           [[p,t] for p in cfg['ET']['probabilities'] for t in cfg['ET']['time_ratios']] if mode=='et' else
           [['PUCT',t] for t in cfg['PUCT']['temperatures']]+[['ALNS',None]])
    for (load,setting),c in configs.items():
        assert len(c['cells'])==36
        macro=np.mean([v[1:]/v[0] for v in c['cells'].values()],axis=0)
        percentile=np.percentile(c['times'],[50,95,99]).tolist()
        key=[-macro[0],-macro[1],macro[2],macro[3],macro[4],percentile[1],order.index(c['setting'])]
        summaries.append(dict(load=load,setting=c['setting'],calls=c['count'],timeouts=c['timeouts'],invalid=c['invalid'],
            macro_online_success=float(macro[0]),macro_normalized_U_exec=float(macro[1]),macro_drop=float(macro[2]),
            macro_add=float(macro[3]),macro_move=float(macro[4]),macro_valid_output=float(macro[5]),
            latency_percentiles_ns=percentile,selection_key=key,
            cells=[dict(layer=l,scenario=s,applicable=int(v[0]),online_success=int(v[1]),normalized_U_exec_sum=float(v[2])) for (l,s),v in c['cells'].items()]))
    selected={load:min((r for r in summaries if r['load']==load),key=lambda r:r['selection_key']) for load in cfg['loads']}
    output=dict(mode=mode,calls=n,selected=selected,configurations=summaries,selection_policy=cfg['selection_order'])
    (run/(mode+'_summary.json')).write_text(json.dumps(output,indent=2)+'\n')
    if mode=='rules':
        fixed=json.loads((run/'grid_summary.json').read_text())['selected']
        freeze={load:dict(fixed=fixed[load]['setting'],rule=dict(name=selected[load]['setting']),rule_adjustments=1) for load in cfg['loads']}
        p=run/'selection_fixed_rule.json'
        assert not p.exists(),'validation rule adjustment cannot be repeated'
        p.write_text(json.dumps(freeze,indent=2)+'\n')
    if mode=='search':
        # PUCT temperatures compete only with other PUCT temperatures.
        output['selected_puct']={load:min((r for r in summaries if r['load']==load and r['setting'][0]=='PUCT'),key=lambda r:r['selection_key']) for load in cfg['loads']}
        (run/'search_summary.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(mode=mode,calls=n,selected=selected),ensure_ascii=False),flush=True)


if __name__=='__main__':summarize(sys.argv[1])
