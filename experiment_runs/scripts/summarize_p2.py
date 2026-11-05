"""Build P2 paired tables and descriptive figures; no further experiments."""
from collections import Counter
import csv
from datetime import datetime,timezone
import hashlib
from importlib.metadata import metadata,distribution
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from isl.p1_sources import save_json


def main():
    run=Path(sys.argv[1]).resolve()
    rows=[json.loads(l) for l in (run/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==200
    audit=json.loads((run/'independent_audit.json').read_text(encoding='utf-8'))
    kinds=['cancellation','urgent_insertion','reward_update'];layers={}
    table=[]
    for row in rows:
        spec,exact,h=row['event_spec'],row['exact'],row['heuristic_50ms']
        c=row['comparisons']['online_50ms']
        table.append({**spec,'exact_status':exact['status'],'urgent_certificate':exact['urgent_certificate'],
            'exact_U':exact['metrics']['U_raw'],'heuristic_U':h['metrics']['U_raw'],
            'utility_gap_to_proven_optimum':c['utility_gap_to_proven_optimum'],
            'full_lexicographic_optimum':c['matches_proven_lexicographic_optimum'],
            'exact_N_drop':exact['metrics']['N_drop'],'heuristic_N_drop':h['metrics']['N_drop'],
            'exact_N_add':exact['metrics']['N_add'],'heuristic_N_add':h['metrics']['N_add'],
            'exact_M_all':exact['metrics']['M_all'],'heuristic_M_all':h['metrics']['M_all'],
            'exact_total_ms':exact['total_ns']/1e6,'heuristic_total_ms':h['total_ns']/1e6,
            'heuristic_status':h['status'],'case_sha256':row['case_sha256']})
    with (run/'per_event_comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    for kind in kinds:
        subset=[r for r in table if r['kind']==kind]
        gaps=[r['utility_gap_to_proven_optimum'] for r in subset]
        layers[kind]={'events':len(subset),'full_lexicographic_optimum':sum(r['full_lexicographic_optimum'] for r in subset),
            'utility_optimum':sum(g==0 for g in gaps),'mean_utility_gap':float(np.mean(gaps)),'max_utility_gap':max(gaps),
            'exact_U_mean':float(np.mean([r['exact_U'] for r in subset])),
            'heuristic_U_mean':float(np.mean([r['heuristic_U'] for r in subset]))}
    first_diff=Counter()
    for row in rows:
        names=['service','utility','N_drop','N_add','M_all']
        first_diff.update([next((names[i] for i,(a,b) in enumerate(zip(row['exact']['selection_key'],row['comparisons']['online_50ms']['heuristic_selection_key'])) if a!=b),'none')])
    analysis={'event_denominator':200,'by_disturbance':layers,'first_lexicographic_difference':dict(first_diff),
              'same_50ms_and_30s_plans':sum(r['heuristic_50ms']['plan']==r['heuristic_30s']['plan'] for r in rows),
              'same_service_tier':sum(r['comparisons']['online_50ms']['same_service_tier'] for r in rows),
              'proven_optimal_gap_denominator':sum(r['exact']['proven_optimal'] for r in rows),
              'timing':audit['timing'],'no_statistical_generalization_or_P6_inference':True,
              'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'summary_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save_json(run/'analysis.json',analysis)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
    titles=['Cancellation (n=67)','Urgent insertion (n=67)','Reward update (n=66)']
    for ax,kind,title in zip(axes,kinds,titles):
        subset=[r for r in table if r['kind']==kind]
        gaps=np.array([r['utility_gap_to_proven_optimum'] for r in subset])
        ax.hist(gaps,bins=np.arange(-.5,121,10),color='#237A91',edgecolor='white')
        ax.set(title=title,xlabel='Utility gap to proven local optimum',ylabel='Events',xlim=(-3,121),ylim=(0,70))
        ax.text(.97,.94,f"Full lexicographic optimum\n{layers[kind]['full_lexicographic_optimum']}/{len(subset)}",ha='right',va='top',transform=ax.transAxes)
    fig.suptitle('P2: Fixed-PALR (w=5, B=2) vs CP-SAT local discrete reference\nAll 200 events proved optimal; all compared within the same service tier',fontsize=12)
    fig.savefig(run/'optimality_gaps.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    counts=[34,34,33,33,33,33];labels=['10 / 4','10 / 8','20 / 4','20 / 8','30 / 4','30 / 8']
    matches=[sum(r['full_lexicographic_optimum'] for r in table if r['combination_index']==ci) for ci in range(6)]
    axes[0].bar(labels,counts,color='#D8E4EB',label='All selected events')
    axes[0].bar(labels,matches,color='#237A91',label='Full lexicographic optimum')
    for i,(m,n) in enumerate(zip(matches,counts)):axes[0].text(i,n+.5,f'{m}/{n}',ha='center')
    axes[0].set(xlabel='Base candidates / satellites',ylabel='Events',ylim=(0,42),title='Same-domain exact alignment');axes[0].legend(loc='upper center',fontsize=8)
    for key,label,color in [('exact','CP-SAT offline','#AC4A24'),('heuristic_50ms','Fixed-PALR 50 ms','#237A91')]:
        values=sorted(r[key]['total_ns']/1e6 for r in rows)
        axes[1].step(values,np.arange(1,201)/200,where='post',label=label,color=color)
    axes[1].set(xlabel='Actual per-event total time (ms)',ylabel='Cumulative fraction',ylim=(0,1.03),title='Single run; Windows / pinned logical CPU')
    axes[1].axvline(50,color='grey',linestyle='--',linewidth=1);axes[1].legend(loc='lower right')
    fig.suptitle('P2 correctness evidence; offline CP-SAT is not a 50 ms online ranking',fontsize=12)
    fig.savefig(run/'alignment_and_timing.png',dpi=170);plt.close(fig)
    packages={}
    for package in ('ortools','protobuf','absl-py','immutabledict','numpy','pandas'):
        meta=metadata(package);licenses={}
        dist=distribution(package)
        for path in dist.files or []:
            if 'license' in str(path).lower() and '.dist-info/' in str(path).replace('\\','/'):
                file=Path(dist.locate_file(path))
                if file.is_file():licenses[str(path)]=hashlib.sha256(file.read_bytes()).hexdigest()
        packages[package]={'version':meta['Version'],'license':meta.get('License'),'license_expression':meta.get('License-Expression'),
                           'project_urls':meta.get_all('Project-URL'),'license_file_sha256':licenses}
    save_json(run/'software_and_data_provenance.json',{'data':'D1 synthetic, P1 distributions; no new external data download',
        'input_directory':'experiment_runs/reports/p2/P2-inputs-v1','raw_orbit_data_read':False,
        'ortools_source':'https://github.com/google/or-tools','packages':packages,
        'dependency_install_note':'ortools 9.14.6206 unavailable for current cp314 Windows; installed and tested available 9.15.6755',
        'new_data_or_software_relicensed':False})
    print(json.dumps(analysis,indent=2))


if __name__=='__main__':main()
