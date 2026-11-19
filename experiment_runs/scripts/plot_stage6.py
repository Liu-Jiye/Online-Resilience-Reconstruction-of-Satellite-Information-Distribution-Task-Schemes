"""Source-linked P6 single-panel scientific figures, editable PDF/SVG and PNG."""
import argparse,subprocess
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from p6_common import *

plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','DejaVu Sans'],'font.size':9,
 'axes.labelsize':10,'axes.titlesize':11,'xtick.labelsize':9,'ytick.labelsize':9,
 'legend.fontsize':8,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,
 'axes.spines.right':False,'legend.frameon':False,'savefig.dpi':300})
FIG=OUT/'figures';FIG.mkdir(parents=True,exist_ok=True)
CONTRACT={
 'F1_main_success':'Rule PALR exceeds the three global search baselines; comparison with fixed PALR remains uncertain.',
 'F2_local_mechanisms':'Same neighborhood and operation budget require a separate mechanism comparison.',
 'F3_A5_controls':'Rule-only ablation does not establish a control advantage over fixed parameters.',
 'F4_shared_upgrades':'Shared 50 ms upgrades need to improve over PALR-only and their search-only counterparts.',
 'F5_load_boundary':'Load increases expose the online deadline boundary.',
 'F6_trajectories':'Delivered utility is compared with the whole trajectory as the independent unit.',
 'F7_legacy_exact_gap':'P2 local discrete certificates quantify an earlier implementation only.',
 'F8_quality_disturbance':'Execution utility and conditional movement describe different populations.',
 'F9_window_sensitivity':'Changed versus original windows are paired by base instance and event.'}

def read(name):return pd.read_csv(OUT/'tables'/name)
def main_effects(phase):
    d=read(phase+'_effects.csv')
    return d[(d.view=='overall')&(d.bootstrap=='hierarchical')]
def export(fig,name,data,source,args):
    fig.canvas.draw()
    path=FIG/name
    if args.qa_tools:
        sys.path.insert(0,str(args.qa_tools))
        from audit_panel_alignment import require_matplotlib_panel_alignment
        require_matplotlib_panel_alignment(fig,json_out=str(path)+'.alignment.json',strict=True)
    else:save(str(path)+'.alignment.json',dict(status='NOT APPLICABLE',reason='Single quantitative axes'))
    fig.savefig(str(path)+'.png',dpi=300)
    fig.savefig(str(path)+'.pdf')
    fig.savefig(str(path)+'.svg')
    data.to_csv(str(path)+'.source.csv',index=False)
    save(str(path)+'.legend.json',dict(conclusion=CONTRACT[name],source=source,archetype='single quantitative panel',
        dimensions_inches=list(fig.get_size_inches()),backend='Python matplotlib',
        independent_unit='Base instance; whole trajectory for F6; P2 legacy event certificate for F7',
        interval='10,000 paired cluster bootstrap, orbital group then instance, percentile 95%; F7 and F8 are descriptive',
        seeds='11,23,47,89,131 averaged within event before resampling; not independent n',
        test='No p values; marginal intervals, no simultaneous coverage',
        render='Editable PDF/SVG plus 300 dpi PNG; no smoothing or invented observations'))
    plt.close(fig)

def forest(data,name,xlabel,args,source):
    data=data.copy().reset_index(drop=True)
    fig,ax=plt.subplots(figsize=(7.2,max(3.6,.38*len(data)+1.4)))
    fig.subplots_adjust(left=.42,right=.96,bottom=.22,top=.88)
    y=np.arange(len(data));ax.axvline(0,color='#999999',lw=.8,zorder=0)
    for i,row in data.iterrows():
        ax.plot([row.ci95_low,row.ci95_high],[i,i],color='#176B8F',lw=1.5)
        ax.plot(row.estimate,i,'o',color='#176B8F',ms=4)
    ax.set_yticks(y,data.display);ax.invert_yaxis();ax.set_xlabel(xlabel)
    ax.set_title(name.replace('_',' '),loc='left',pad=13)
    ax.tick_params(axis='y',length=0)
    export(fig,name,data,source,args)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--qa-tools',type=Path);args=parser.parse_args()
    save(FIG/'figure_contract.json',dict(backend='Python, reused from existing project plotting workflow',
        figures=CONTRACT,policy='Predefined contrasts shown without selecting by sign or interval; all other contrasts in tables',
        architecture='Independent single-panel figures; no composite alignment issue',glyph_floor_pt=5))
    for phase,name,left,rights in [
        ('P4','F1_main_success','Rule-PALR',['Minimal-Repair','Frozen-Greedy','Fixed-PALR','Validation-Best-Fixed','PUCT-ISL','ALNS-ISL','CP-SAT-50ms']),
        ('mechanisms','F2_local_mechanisms','PALR-local',['PUCT-local','ALNS-local','CP-local']),
        ('ablations','F3_A5_controls','Rule-PALR',['Grid-w5-B2','Grid-w5-B1','B-only','w-only'])]:
        d=main_effects(phase);d=d[(d.left==left)&d.right.isin(rights)&(d.metric=='online_success')].copy()
        d=d.set_index('right').loc[rights].reset_index();d['display']=left+' vs '+d.right
        d[['estimate','ci95_low','ci95_high']]*=100
        forest(d,name,'Online success difference (percentage points)',args,phase+'_effects.csv')
    d=main_effects('upgrades');d=d[d.metric=='online_success'].copy();d['display']=d.left+' vs '+d.right
    d[['estimate','ci95_low','ci95_high']]*=100
    forest(d,'F4_shared_upgrades','Online success difference (percentage points)',args,'upgrades_effects.csv')
    d=read('single_factor_statistics.csv');d=d[(d.view=='overall')&(d.bootstrap=='hierarchical')&(d.metric=='online_success')&d.condition.str.startswith('N|')].copy()
    d['load']=d.condition.str.split('|').str[1].astype(float)
    fig,ax=plt.subplots(figsize=(7.2,4.4));fig.subplots_adjust(left=.12,right=.96,bottom=.18,top=.9)
    labels=['Minimal-Repair','Fixed-PALR','Validation-Best-Fixed','Rule-PALR'];colors=['#777777','#267CB0','#A27719','#16664E']
    for offset,(label,color) in enumerate(zip(labels,colors)):
        g=d[d.label==label].sort_values('load');x=np.arange(len(g))+(offset-1.5)*.14
        ax.errorbar(x,g.estimate*100,yerr=np.stack([(g.estimate-g.ci95_low)*100,(g.ci95_high-g.estimate)*100]),fmt='o',ms=4,color=color,label=label,capsize=2)
    ax.set_xticks(range(5),['50','100','200','500','1000']);ax.set_xlabel('Task count N');ax.set_ylabel('Online success (%)');ax.set_ylim(-3,103)
    ax.legend(loc='lower left');export(fig,'F5_load_boundary',d,'single_factor_statistics.csv',args)
    d=read('trajectory_effects.csv');d=d[(d.bootstrap=='hierarchical')&(d.left=='Rule-PALR')&(d.metric=='delivered_utility')].copy();d['display']='Rule-PALR vs '+d.right
    forest(d,'F6_trajectories','Delivered utility difference per trajectory',args,'trajectory_effects.csv')
    d=pd.read_csv(SOURCE/'reports/p2/P2-20261105T114327Z/per_event_comparison.csv');fig,ax=plt.subplots(figsize=(7.2,3.8));fig.subplots_adjust(left=.13,right=.95,bottom=.2,top=.88)
    counts=d.groupby('utility_gap_to_proven_optimum').size();ax.bar(counts.index,counts.values,color='#176B8F',width=1.6)
    ax.set_xlabel('P2 utility gap to certified local optimum');ax.set_ylabel('Number of events (200 total)')
    export(fig,'F7_legacy_exact_gap',d,'P2_exact_gap_legacy.csv',args)
    d=read('P4_statistics.csv');d=d[(d.view=='overall')&(d.bootstrap=='hierarchical')].pivot(index='label',columns='metric',values='estimate').reset_index()
    fig,ax=plt.subplots(figsize=(7.2,4.2));fig.subplots_adjust(left=.13,right=.60,bottom=.2,top=.92)
    for i,row in d.iterrows():
        ax.scatter(row.conditional_M_all,row.U_exec,s=24,marker=['o','s','^','D','v','P','X','*'][i],label=row.label)
    ax.legend(loc='center left',bbox_to_anchor=(1.03,.5))
    ax.margins(x=.45,y=.25);ax.set_xlabel('Mean movement among valid outputs (s)');ax.set_ylabel('Mean execution utility (all applicable events)')
    export(fig,'F8_quality_disturbance',d,'P4_statistics.csv; descriptive trade-off, different denominators on axes',args)
    d=read('paired_condition_sensitivity.csv');d=d[(d.phase=='windows')&(d.label=='Rule-PALR')&(d.metric=='online_success')&(d.bootstrap=='hierarchical')].copy()
    d['display']=d.variant;d[['estimate','ci95_low','ci95_high']]*=100
    forest(d,'F9_window_sensitivity','Changed minus original success (percentage points)',args,'paired_condition_sensitivity.csv')
    if args.qa_tools:
        qa=FIG/'qa';qa.mkdir(exist_ok=True)
        command=[sys.executable,str(args.qa_tools/'validate_figure.py'),str(Path(__file__)),'--json']
        result=subprocess.run(command,capture_output=True,text=True);(qa/'source_preflight.json').write_text(result.stdout,encoding='utf-8')
        for pdf in sorted(FIG.glob('*.pdf')):
            for script,suffix,extra in [('audit_pdf_text.py','text',['--min-pt','5','--json']),('audit_figure_collisions.py','collisions',['--json-out',str(qa/(pdf.stem+'.collisions.json'))])]:
                result=subprocess.run([sys.executable,str(args.qa_tools/script),str(pdf)]+extra,capture_output=True,text=True)
                (qa/(pdf.stem+'.'+suffix+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
                print(pdf.stem,suffix,result.returncode,flush=True)

if __name__=='__main__':main()
