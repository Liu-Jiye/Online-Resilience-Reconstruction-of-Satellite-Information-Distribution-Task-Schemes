"""Derived P2-C tables and figure; never rewrites frozen observations."""
from pathlib import Path
from collections import Counter
import argparse,csv,hashlib,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args();out=Path(args.folder)
    rows=[json.loads(x) for x in (out/'results.jsonl').read_text().splitlines()]
    records=[];timeouts=[]
    for row in rows:
        for method,r in row['results'].items():
            h='PALR' in method;valid=(r.get('validation') or (r.get('certificate') or {}).get('validation') or {}).get('feasible',False)
            service=valid and any(p['task_id']=='urgent' for p in (r['plan'] or []))
            rec={'entry':row['entry'],'group':row['group'],'method':method,'status':r['status'],'service_success':service,
                 'valid_plan':valid,'total_ms':r['total_ns']/1e6,'timeout':r['status']=='timeout',
                 'urgent_certificate':r.get('urgent_certificate'),'online_success':r['metrics'].get('online_success') if h else None,
                 **{k:r['metrics'][k] for k in ('U_raw','N_drop','N_add','M_all')}}
            records.append(rec)
            if rec['timeout']:timeouts.append(rec)
    with (out/'per_event_detailed.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    methods=sorted({r['method'] for r in records})
    detail={'observations':len(records),'PALR_runs':sum('PALR' in r['method'] for r in records),
            'exact_runs':sum('exact' in r['method'] for r in records),'timeouts':timeouts,
            'all_plans_valid':all(r['valid_plan'] for r in records),'core_events':150,
            'timings':{method:{'n':len(v:=[r for r in records if r['method']==method]),
                'mean_ms':float(np.mean([r['total_ms'] for r in v])),
                'p95_ms':float(np.percentile([r['total_ms'] for r in v],95)),
                'max_ms':max(r['total_ms'] for r in v)} for method in methods},
            'exact_actual_over30s':sum(r.get('actual_total_exceeds_30s',False) for row in rows for r in row['results'].values()),
            'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'P3_started':False,'population_statistical_claims':False}
    (out/'analysis.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    groups=['direct','single','double','triple','outside','hard'];counts=[25,50,25,25,50,25]
    names=['Direct control','One deletion','Two deletions','Three deletions','Outside w5','Hard control']
    shown=['v1_PALR_w5','v2_PALR_w5','v2_exact_w5','v2_PALR_w20','v2_exact_w20']
    values=np.full((6,5),np.nan)
    for i,g in enumerate(groups):
        for j,m in enumerate(shown):
            subset=[r for r in records if r['group']==g and r['method']==m]
            if subset:values[i,j]=sum(r['service_success'] for r in subset)/len(subset)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,5),gridspec_kw={'width_ratios':[1,1.8]},layout='constrained')
    ax=axes[0];ax.barh(range(6),counts,color=['#7A8F9C','#237A91','#237A91','#237A91','#237A91','#7A8F9C']);ax.invert_yaxis()
    ax.set(yticks=range(6),yticklabels=names,xlabel='Certified events',xlim=(0,60),title='150 core challenges + 50 controls')
    for i,n in enumerate(counts):ax.text(n+1,i,str(n),va='center')
    ax=axes[1];ax.imshow(np.ma.masked_invalid(values),cmap='Blues',vmin=0,vmax=1,aspect='auto')
    ax.set(yticks=range(6),yticklabels=names,xticks=range(5),xticklabels=['v1 PALR\nw5','v2 PALR\nw5','v2 exact\nw5','v2 PALR\nw20','v2 exact\nw20'],title='Service successes / events (by mechanism)')
    for i in range(6):
        for j in range(5):ax.text(j,i,'N/A' if np.isnan(values[i,j]) else f'{round(values[i,j]*counts[i])}/{counts[i]}',ha='center',va='center',color='white' if values[i,j]>.5 else 'black')
    fig.suptitle('P2-C controlled fixtures: coverage completed; operator and neighborhood limits exposed',fontsize=12)
    fig.savefig(out/'P2C_coverage_and_results.png',dpi=180);plt.close(fig)
    print(json.dumps(detail,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
