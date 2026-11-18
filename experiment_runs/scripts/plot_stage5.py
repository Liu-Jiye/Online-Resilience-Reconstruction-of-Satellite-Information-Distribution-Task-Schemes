"""Standalone reproducible P5 figures, all values read from exported evidence tables."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from p5_common import *

T=OUT/'tables';F=OUT/'figures';F.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':300,'pdf.fonttype':42})
COLORS=['#0072B2','#D55E00','#009E73','#CC79A7','#E69F00','#56B4E9']

def read(n):return pd.read_csv(T/n)
def finish(fig,name):
    fig.tight_layout();fig.savefig(F/(name+'.png'));fig.savefig(F/(name+'.pdf'));plt.close(fig)

def main():
    a=read('ablations_summary.csv');e=read('ablations_events.csv.gz')
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    for kind,color in zip(('all','cancellation','urgent_insertion','reward_update'),COLORS):
        x=e if kind=='all' else e[e.kind==kind]
        for ax,labels,values,title,xlabel in [(axes[0],[f'Grid-w5-B{b}' for b in (0,1,2,3,5)],[0,1,2,3,5],'A3: admission budget (w=5)','B'),(axes[1],[f'Grid-w{w}-B2' for w in (1,3,5,10,20)],[1,3,5,10,20],'A4: neighborhood size (B=2)','w')]:
            rates=[x[(x.label==l)&(x.applicable>0)].online_success.mean() for l in labels]
            ax.plot(values,rates,'o-',label=kind,color=color);ax.set(title=title,xlabel=xlabel,ylabel='Online success rate',ylim=(0,1));ax.grid(alpha=.2)
    axes[1].legend(fontsize=8);finish(fig,'ablation_B_w')
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    labels=['Grid-w5-B2','B-only','w-only','Rule-PALR'];names=['Fixed w5/B2','B only','w only','Joint rule'];s=a.set_index('label').loc[labels]
    axes[0].bar(names,s.online_success,color=COLORS[:4]);axes[0].set(ylabel='Online success rate',ylim=(0,1),title='A5: rule-control ablation')
    axes[1].bar(names,s.p95_ms,color=COLORS[:4]);axes[1].axhline(50,ls='--',color='gray',lw=1);axes[1].set(ylabel='Full-call p95 (ms)',title='Latency includes controller and return')
    for ax in axes:ax.tick_params(axis='x',rotation=15)
    finish(fig,'A5_rule_control')
    fig,axes=plt.subplots(1,3,figsize=(13,3.5),sharey=True)
    for ax,layer in zip(axes,('D1','D2-S','D2-O')):
        for name,color,style in [('Rule-PALR',COLORS[0],'-'),('No-time',COLORS[1],'--')]:
            rates=[e[(e.label==f'{name}@{b}ms')&(e.layer==layer)&(e.applicable>0)].online_success.mean() for b in (5,10,20,50,100)]
            ax.plot([5,10,20,50,100],rates,'o'+style,color=color,label=name)
        ax.set(title=layer,xlabel='Total response budget (ms)',ylim=(0,1));ax.set_xscale('log');ax.set_xticks([5,10,20,50,100],['5','10','20','50','100']);ax.grid(alpha=.2)
    axes[0].set_ylabel('Online success rate');axes[2].legend(fontsize=8);finish(fig,'A10_response_budget')
    s=read('single_factor_summary.csv');fig,axes=plt.subplots(2,4,figsize=(15,7),sharey=True)
    factors=['N','FR','span','hotspot','distance','rate','calendar']
    for ax,factor in zip(axes.flat,factors):
        part=s[s.factor==factor]
        for name,color in zip(LIGHT,COLORS):
            g=part[part.label==name].sort_values('value');ax.plot(g.value,g.online_success,'o-',label=name,color=color)
        ax.set(title=factor+(' (D2 only)' if factor=='distance' else ''),xlabel=factor,ylabel='Online success rate',ylim=(0,1));ax.grid(alpha=.2)
        if factor=='N':ax.set_xscale('log');ax.set_xticks([50,100,200,500,1000],['50','100','200','500','1000'])
    axes.flat[-1].axis('off');handles,labels=axes.flat[0].get_legend_handles_labels();axes.flat[-1].legend(handles,labels,loc='center',frameon=False)
    finish(fig,'single_factor_success')
    w=read('windows_FR_q.csv');g=w[w.label=='Rule-PALR'].groupby(['variant','FR'])[['success_equivalent','applicable']].sum();g['rate']=g.success_equivalent/g.applicable
    matrix=g.rate.unstack('FR');fig,ax=plt.subplots(figsize=(7,4.7));im=ax.imshow(matrix.values,vmin=0,vmax=1,cmap='cividis',aspect='auto')
    ax.set_xticks(range(len(matrix.columns)),[str(x) for x in matrix.columns]);ax.set_yticks(range(len(matrix)),matrix.index);ax.set(xlabel='Frozen fraction',title='Joint rule: paired window stress')
    for i in range(len(matrix)):
        for j in range(len(matrix.columns)):ax.text(j,i,f'{matrix.iloc[i,j]:.1%}',ha='center',va='center',color='white' if matrix.iloc[i,j]<.5 else 'black')
    fig.colorbar(im,ax=ax,label='Online success rate');finish(fig,'FR_window_stress')
    # Conditional valid-output quality shown separately by disturbance scale.
    k=read('ablations_by_kind.csv');labels=['Minimal-Repair','Grid-w5-B2','Grid-w5-B1','Rule-PALR'];fig,axes=plt.subplots(3,3,figsize=(12,9))
    for i,kind in enumerate(('cancellation','urgent_insertion','reward_update')):
        for j,xfield in enumerate(('conditional_N_drop','conditional_N_add','conditional_M_all')):
            ax=axes[i,j]
            for label,color in zip(labels,COLORS):
                row=k[(k.label==label)&(k.kind==kind)].iloc[0];ax.scatter(row[xfield],row.conditional_U,color=color,label=label,s=45)
            ax.set(xlabel=xfield.removeprefix('conditional_'),ylabel='Conditional valid-output utility',title=kind);ax.grid(alpha=.2)
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',ncol=4,fontsize=9);fig.tight_layout(rect=[0,0,1,.96]);fig.savefig(F/'utility_disturbance.png');fig.savefig(F/'utility_disturbance.pdf');plt.close(fig)
    m=read('mechanisms_summary.csv');u=read('upgrades_summary.csv');fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,data,title in [(axes[0],m,'Same E / B2 mechanism comparison'),(axes[1],u,'Shared 50 ms upgrade comparison')]:
        data=data.sort_values('online_success',ascending=False);ax.bar(data.label,data.online_success,color=COLORS[:len(data)]);ax.set(ylabel='Online success rate',ylim=(0,1),title=title);ax.tick_params(axis='x',rotation=25)
    finish(fig,'mechanisms_and_upgrades')
    save(F/'figure_provenance.json',dict(source_tables={p.name:sha(p) for p in T.glob('*.csv*')},
        notes='Seed means within event; applicable conditions retained; conditional utility and interference exclude invalid/late outputs and have exported denominators; no hard real-time claim',
        plots=['ablation_B_w','A5_rule_control','A10_response_budget','single_factor_success','FR_window_stress','utility_disturbance','mechanisms_and_upgrades']))

if __name__=='__main__':main()
