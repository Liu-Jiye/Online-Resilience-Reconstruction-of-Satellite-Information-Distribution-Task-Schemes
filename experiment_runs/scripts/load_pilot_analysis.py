"""Publish descriptive load-pilot evidence without modifying frozen observations."""
from pathlib import Path
from collections import Counter
import argparse,csv,hashlib,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args();out=Path(args.folder)
    rows=json.loads((out/'context_rows.json').read_text(encoding='utf-8'))
    means=json.loads((out/'group_means.json').read_text(encoding='utf-8'))
    config=json.loads((out/'config.json').read_text(encoding='utf-8'))
    summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
    def group(split,layer,N,h):return means[f'{split}|{layer}|{N}|{h:.1f}']
    def subset(split,layer,N,h):return [r for r in rows if r['split']==split and r['layer']==layer and r['N']==N and r['h']==h]
    flat=[]
    for key,value in means.items():
        split,layer,N,h=key.split('|');flat.append({'split':split,'layer':layer,'N':N,'h':h,**value})
    with (out/'group_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    focus=[];probes=[]
    for split in config['splits']:
        for layer in config['layers']:
            for name,N,h in [('default',100,0.),('medium',500,.8)]:
                chosen=subset(split,layer,N,h);g=group(split,layer,N,h)
                focus.append({'split':split,'layer':layer,'configuration':name,**g,
                    'competition_min':min(r['competition_fraction'] for r in chosen),
                    'competition_p25':float(np.percentile([r['competition_fraction'] for r in chosen],25)),
                    'competition_median':float(np.median([r['competition_fraction'] for r in chosen])),
                    'competition_p75':float(np.percentile([r['competition_fraction'] for r in chosen],75)),
                    'competition_max':max(r['competition_fraction'] for r in chosen),
                    'blocked_candidate_total':sum(r['blocked_count'] for r in chosen),
                    'fixed_blocker_counts':{str(k):sum(r[f'fixed_blockers_{k}'] for r in chosen) for k in ('1','2','3plus')}})
                for kind in ('natural','opportunity'):
                    for fr in ('0','0.6'):
                        counts=Counter()
                        for r in chosen:counts.update(r[f'{kind}_FR{fr}'])
                        probes.append({'split':split,'layer':layer,'configuration':name,'kind':kind,'FR':fr,'total':sum(counts.values()),**dict(counts)})
    analysis={'base_clusters':150,'contexts':len(rows),'focus':focus,'probe_tables':probes,
        'selection':summary['selection'],'independent_events_claimed':False,
        'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(out/'analysis.json',analysis)
    with (out/'probe_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(probes[0]));w.writeheader();w.writerows(probes)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(13.5,4.5),layout='constrained',sharey=True)
    colors=['#3985A3','#DC9E36','#C14757']
    for ax,layer in zip(axes,config['layers']):
        ax.axhspan(10,35,color='#dcebdc',alpha=.65);ax.axhline(25,color='#8b8b8b',ls=':',lw=1)
        for h,color in zip(config['hot_probabilities'],colors):
            for split,style,marker in [('train','-','o'),('validation','--','s')]:
                ax.plot(config['task_counts'],[group(split,layer,N,h)['competition_fraction']*100 for N in config['task_counts']],
                    color=color,ls=style,marker=marker,label=f'h={h:.1f}, {split}')
        ax.set(title=layer,xlabel='Demand tasks N',xticks=config['task_counts'],ylim=(0,37));ax.grid(alpha=.15)
    axes[0].set_ylabel('Blocked / calendar-feasible candidates (%)');axes[-1].legend(fontsize=8,loc='upper left')
    fig.suptitle('Load pilot: only N=500, h=0.8 passes the medium criteria in all three layers')
    fig.savefig(out/'load_competition_grid.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13.5,4.5),layout='constrained')
    val=[v for v in focus if v['split']=='validation'];x=np.arange(3)
    for ax,field,title in zip(axes,['competition_fraction','opportunity_probe_blocked_fraction','hot_terminal_occupancy'],
                              ['Candidate competition','Opportunity probe blocking (FR=0)','Scheduled hot-terminal occupancy']):
        for name,offset,color in [('default',-.18,'#8498A5'),('medium',.18,'#237A91')]:
            v=[next(v[field]*100 for v in val if v['layer']==layer and v['configuration']==name) for layer in config['layers']]
            bars=ax.bar(x+offset,v,.34,color=color,label=name)
            ax.bar_label(bars,fmt='%.1f',padding=3,fontsize=9)
        ax.set(xticks=x,xticklabels=config['layers'],ylabel='%',title=title);ax.set_ylim(0,ax.get_ylim()[1]*1.15)
    axes[0].legend();fig.suptitle('Validation confirmation: 25 base scenes per layer; paired default versus frozen medium')
    fig.savefig(out/'load_validation_comparison.png',dpi=180);plt.close(fig)
    report=['# 训练／验证负载试点报告：P1 补充，未进入 P3','',
        '本轮保留既有默认自然数据，完成预先冻结的 9 配置训练／验证负载试点。**新增中竞争层已通过并冻结：N=500、热点分支概率 h=0.8、每场景 4 颗热点星。高竞争层没有训练合格配置，未冻结。**没有运行修复算法、CP-SAT 或测试实例。','',
        '## 范围与预注册','',
        f'批次：`{out.name}`。协议、实现和选层阈值先在 Git 提交 `8bffdc7` 固定；生成产物及选层在提交 `478aba8` 固定，随后执行独立审计。完整冻结协议见 `protocol/LOAD_PILOT_V1_CONTRACT.md`，运行配置见本批次 `config.json`。','',
        '复用原 P1 的 150 个场景，每层 25 训练＋25 验证；卫星、接触、轨道来源、片段及背景日历保持原值，不下载新快照。9 配置为任务数 100／200／500 × 热点概率 0／0.5／0.8。1,350 个上下文全部成功，训练 675、验证 675，生成失败 0；它们共享 150 个基础场景簇，不能当作 1,350 个独立样本。N100/h0 的 150 组任务与参考计划逐项重现原 P1。','',
        '同一 h 的需求是嵌套前缀；跨 h 保留任务 ID、数据量、速率、效用、名义窗长和抽样类别，热点分支改变端点与窗口锚点。热点星均匀无放回选取，不依据轨道度数或算法结果。背景忙概率仍为 0.5。h 是热点分支概率，不是实际热点端点份额。','',
        '## 指标与选层规则','',
        '竞争比例定义为“自身满足接触、任务窗和背景日历、但被固定参考计划阻塞的未排候选数／全部自身满足接触、任务窗和日历的候选数”，每组按 25 场景等权平均。日历、双方终端半双工、整数开始时刻和单窗口约束与原离散模型一致。','',
        '中竞争门槛为竞争比例 10%～35%、平均阻塞候选≥5、FR0 机会条件探针阻塞率≥10%；高竞争为 25%～70%、≥15、≥25%。共同要求物理机会比例≥65%、日历机会比例≥30%，二者相对默认下降均不超过 10 个百分点，每例 20 个机会条件探针；同一配置须在三个数据层同时通过。高层还须 N 不低于中层且每层竞争比例至少比中层高 10 个百分点。按 N 再 h 升序选择。','',
        '训练 675 个配置完成后、开始验证场景前保存 `training_selection.json`。中层只有 N500/h0.8 同时通过全部训练门槛。验证只确认此候选，三个数据层均通过；没有按验证结果改选。高层训练无人合格，最大配置在三层竞争比例仍低于 25%，且不能提供规定的中高间距。未放宽阈值、未扩展网格。','',
        '## 默认与新增层的竞争','',
        '| 划分 | 数据层 | 默认竞争比例 | 新增竞争比例 | 默认平均阻塞数 | 新增平均阻塞数 | 新增机会探针阻塞率 FR0 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for split in config['splits']:
        for layer in config['layers']:
            b=group(split,layer,100,0.);m=group(split,layer,500,.8)
            report.append(f"| {split} | {layer} | {b['competition_fraction']:.2%} | {m['competition_fraction']:.2%} | {b['blocked_count']:.2f} | {m['blocked_count']:.2f} | {m['opportunity_probe_blocked_fraction']:.2%} |")
    report+=['','新增层的平均阻塞候选从约 1 个增至 39～57 个，验证的机会条件请求阻塞率为 27.4%～43.6%。这些是资源竞争诊断，不是修复服务成功率；候选池更大不证明实际预算 B 已绑定。','',
        '![负载网格](p1/'+out.name+'/load_competition_grid.png)','',
        '| N | h | 训练 D1 | 训练 D2-S | 训练 D2-O | 验证 D1 | 验证 D2-S | 验证 D2-O |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for N in config['task_counts']:
        for h in config['hot_probabilities']:
            values=[f"{group(split,layer,N,h)['competition_fraction']:.2%}" for split in config['splits'] for layer in config['layers']]
            report.append('| '+f'{N} | {h:.1f} | '+' | '.join(values)+' |')
    report+=['','以上公开完整网格便于核验分布，验证网格未用于再次选层。','',
        '## 物理机会、日历与端点占用','',
        '| 划分 | 数据层 | 新增物理可行比例 | 新增日历可行比例 | 新增平均排入数 | 新增热点端点份额 | 新增热点终端计划占用 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for split in config['splits']:
        for layer in config['layers']:
            m=group(split,layer,500,.8)
            report.append(f"| {split} | {layer} | {m['window_fraction']:.2%} | {m['calendar_fraction']:.2%} | {m['scheduled_count']:.2f} | {m['actual_hot_endpoint_share']:.2%} | {m['hot_terminal_occupancy']:.2%} |")
    report+=['','全终端计划占用约 2.8%～4.1%，热点终端约 8.8%～13.5%，均未包含背景日历占用。全时域平均占用仍不高，但有窗口的任务已产生可观的同端点局部竞争；不能以此宣称整个网络饱和。物理及日历机会没有因热点设置大幅减少，全部通过事先设置的退化门槛。','',
        '![验证对比](p1/'+out.name+'/load_validation_comparison.png)','',
        '## 自然探针与机会条件探针分开解释','',
        '每配置分别生成 20 个原分布自然紧急探针和 20 个机会条件请求，并在 FR0/0.6 各诊断一次。自然探针沿用 release=0、deadline=600/120，不因其缺少物理机会而替换；机会条件请求从独立母序列后半段按顺序、只依据接触与日历资格选取，所有拒绝尝试保留。全部上下文均找到 20 个机会请求，未触及不足额门槛。','',
        '| 划分 | 数据层 | 类型 | 新增 FR | 无物理机会 | 日历阻塞 | 直接可插 | 可编辑阻塞 | 冻结阻塞 | 总数 |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for p in probes:
        if p['configuration']=='medium':
            report.append('| '+' | '.join(str(p[k]) for k in ('split','layer','kind','FR','no_physical','calendar_blocked','direct','editable_blocked','frozen_blocked','total'))+' |')
    report+=['','每格 500 探针是 25 基场景各 20 个，FR 两次以及不同 N/h 的共同探针不能重复计为独立自然事件。`probe_summary.csv` 另列默认层对应分母。自然请求中仍有大量无物理机会；本轮改善的是有机会任务之间的资源竞争，不能据此声称原自然紧急有效请求稀少的问题自动消失，也不能把机会条件请求当作自然紧急分布。','',
        '固定参考计划的最小同时冲突任务数按不同任务 ID 去重，双端重复只计一次。这表示固定位置插入需解除的阻塞，不等于允许联合移动后的最少删除数，不是全局不可行或最优证书。FR0.6 按精确 floor(0.6×原计划长度) 冻结原排序前缀。','',
        '## 审计、版本与复现','',
        '独立位集实现重建 1,350 个上下文，重放 360,000 个参考贪心决策，交叉核对 360,000 个候选诊断和 108,000 个探针×FR 标签，150 个默认计划与旧证据一致。任务生成、热点种子、探针接受／拒绝、逐上下文统计、训练选择和验证结果均复算。原 P2 及其补充、P1 当前验收维护清单的文件哈希全数保持原值。','',
        '本轮回归 188 项通过；P1 当前公开入口完整通过。原 P1 历史进度文档与 P2 当前版本的三项迁移仍由已有显式兼容协议核验，未修改旧验收。新增内容全部位于 experiment_runs，旧源码与数据未改写。来源归档 SHA-256：`'+config['source_archive_sha256']+'`。环境见 environment.json；运行的约 61 秒仅为离线生成与诊断，不是在线 50ms 性能证据。','',
        '从仓库根目录执行：','',
        '```powershell',
        'experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/verify_load_pilot.py experiment_runs/reports/p1/'+out.name,
        'experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/verify_load_pilot.py experiment_runs/reports/p1/'+out.name+' --full',
        '```','',
        '第一条只读核验最终清单、来源、原产物和旧阶段证据；第二条在临时工作副本中重新执行完整位集审计，比较全部计数后自动清理副本，不覆盖任何公开回执。最终补充验收清单 acceptance_manifest.json 包含源码、报告、表格、图和审计证据哈希。','',
        '## 停点与适用范围','',
        '本轮按预定规则补足了跨三数据层可复核的中竞争负载条件；保留默认层作为自然基准，二者分别报告。高竞争层未通过，不宣称高负载机制覆盖完成。没有进入 P3，没有用修复性能反向选择数据，没有替换旧 P2 或 P2-C。后续是否另开高竞争试点、是否将新增中层纳入后续正式实验，应由用户决定；本轮不自动扩网格或启动下一阶段。','']
    (out.parents[1]/'LOAD_PILOT_REPORT.md').write_text('\n'.join(report),encoding='utf-8',newline='\n')
    print(json.dumps({'analysis':str(out/'analysis.json'),'report':str(out.parents[1]/'LOAD_PILOT_REPORT.md')},ensure_ascii=False))


if __name__=='__main__':main()
