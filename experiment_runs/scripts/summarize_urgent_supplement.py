"""Create cohort-separated tables and figures for the approved supplement."""
from collections import Counter
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from isl.p1_sources import save_json


def main():
    run=Path(sys.argv[1]).resolve()
    rows=[json.loads(l) for l in (run/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
    table=[];analysis={'cohorts':{},'pressure_groups':{},'P3_started':False}
    for row in rows:
        spec=row['event_spec'];out={'cohort':spec['cohort'],'entry':spec['entry'],'category':spec.get('category'),
            'instance_id':row['results']['v2_PALR']['instance_id'],'case_sha256':row['case_sha256'],
            'independent_label':row['independent_urgent_label']['category'],
            'min_removals_w5':row['independent_urgent_label']['min_removals_w5']}
        for v in ('v1','v2'):
            h,e=row['results'][v+'_PALR'],row['results'][v+'_exact']
            out.update({f'{v}_PALR_service':h['metrics']['service_success'],f'{v}_PALR_online_service':h['metrics']['online_success'],
                f'{v}_PALR_status':h['status'],f'{v}_exact_service':e['urgent_certificate'],f'{v}_exact_status':e['status'],
                f'{v}_PALR_ms':h['total_ns']/1e6,f'{v}_exact_ms':e['total_ns']/1e6})
            for metric in ('U_raw','N_drop','N_add','M_all'):out[f'{v}_{metric}']=h['metrics'][metric]
        table.append(out)
    with (run/'per_event_comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    for cohort in ('old_replay','natural','pressure'):
        subset=[r for r in rows if r['event_spec']['cohort']==cohort]
        values={'events':len(subset),'labels':dict(Counter(r['independent_urgent_label']['category'] for r in subset)),
                'gained_service_entries':[r['event_spec']['entry'] for r in subset if not r['results']['v1_PALR']['metrics']['service_success'] and r['results']['v2_PALR']['metrics']['service_success']],
                'versions':{}}
        for v in ('v1','v2'):
            hs=[r['results'][v+'_PALR'] for r in subset];es=[r['results'][v+'_exact'] for r in subset]
            times=[h['total_ns']/1e6 for h in hs]
            values['versions'][v]={'PALR_ms_mean':float(np.mean(times)),'PALR_ms_p95':float(np.quantile(times,.95)),
                'PALR_ms_max':max(times),'exact_ms_max':max(e['total_ns']/1e6 for e in es),
                'all_valid_plans':sum(h['validation']['feasible'] for h in hs),
                'exact_actual_over_30s':sum(e['actual_total_exceeds_30s'] for e in es),
                'full_optimum_match':sum(r['comparisons'][v].get('full_optimum_match') is True for r in subset)}
        analysis['cohorts'][cohort]=values
    for cat in ('direct_insert','one_removal','multiple_removals','outside_neighborhood'):
        subset=[r for r in rows if r['event_spec'].get('category')==cat]
        analysis['pressure_groups'][cat]={'events':len(subset),
             **{f'{v}_PALR_service_success':sum(r['results'][v+'_PALR']['metrics']['service_success'] for r in subset) for v in ('v1','v2')},
             **{f'{v}_exact_service_feasible':sum(r['results'][v+'_exact']['urgent_certificate']=='service_feasible' for r in subset) for v in ('v1','v2')}}
    analysis.update(created_at_utc=datetime.now(timezone.utc).isoformat(),summary_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    pressure_target_satisfied=False,pressure_shortfall=48,statistical_or_main_test_claims=False)
    save_json(run/'analysis.json',analysis)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
    labels=['Original replay\n(n=67)','New natural\n(n=200)'];x=np.arange(2)
    axes[0].bar(x-.18,[3,9],width=.36,color='#7A8F9C',label='v1 PALR')
    axes[0].bar(x+.18,[7,20],width=.36,color='#237A91',label='v2 PALR')
    for i,(a,b) in enumerate(zip([3,9],[7,20])):
        axes[0].text(i-.18,a+.35,str(a),ha='center');axes[0].text(i+.18,b+.35,str(b),ha='center')
    axes[0].set(xticks=x,xticklabels=labels,ylabel='Service successes',ylim=(0,25),title='Natural cohorts remain separate');axes[0].legend(loc='upper left')
    pressure=summary['input_summary']['pressure'];cats=list(analysis['pressure_groups']);n=[pressure[c]['accepted'] for c in cats]
    axes[1].bar(np.arange(4),[25]*4,color='#D8E4EB',label='Target per group')
    axes[1].bar(np.arange(4),n,color='#AC4A24',label='Actually collected')
    for i,value in enumerate(n):axes[1].text(i,max(value,0)+.5,f'{value}/25',ha='center')
    axes[1].set(xticks=np.arange(4),xticklabels=['Direct','One removal','Multiple\nremovals','Outside E'],ylabel='Pressure events',ylim=(0,32),title='Pressure targets: 52 / 100 collected');axes[1].legend(loc='upper right',fontsize=8)
    fig.suptitle('P2 urgent supplement: eligibility-only correction; pressure shortfalls disclosed',fontsize=12)
    fig.savefig(run/'service_and_shortfall.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.3),layout='constrained')
    cats=cats[:3];x=np.arange(3)
    ax.bar(x-.22,[analysis['pressure_groups'][c]['v1_PALR_service_success'] for c in cats],width=.22,color='#7A8F9C',label='v1 PALR')
    ax.bar(x,[analysis['pressure_groups'][c]['v2_PALR_service_success'] for c in cats],width=.22,color='#237A91',label='v2 PALR')
    ax.bar(x+.22,[analysis['pressure_groups'][c]['v2_exact_service_feasible'] for c in cats],width=.22,color='#AC4A24',label='v2 exact local domain')
    ax.set(xticks=x,xticklabels=['Direct insertion (n=25)','One removal (n=25)','Multiple removals (n=2)'],ylabel='Service successes',ylim=(0,31),title='Conditional pressure evidence; no outside-E instances collected')
    ax.legend(loc='upper right');fig.savefig(run/'pressure_service.png',dpi=180);plt.close(fig)
    print(json.dumps({'pressure':analysis['pressure_groups'],'shortfall':48},indent=2))


if __name__=='__main__':main()
