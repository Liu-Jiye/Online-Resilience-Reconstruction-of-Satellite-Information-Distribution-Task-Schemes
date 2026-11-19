"""Generate P6 evidence-bounded Chinese result documents and reproducibility guide."""
import pandas as pd
from p6_common import *

def read(name):return pd.read_csv(OUT/'tables'/name)
def md(df):
    def text(v):
        if pd.isna(v):return '未定义'
        if isinstance(v,float):return f'{v:.4f}'
        return str(v).replace('|',' / ')
    values=[[text(v) for v in row] for row in df.to_numpy()]
    return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(row)+' |' for row in values)

def effects(phase,metric='online_success',left=None,rights=None):
    d=read(phase+'_effects.csv');d=d[(d.view=='overall')&(d.bootstrap=='hierarchical')&(d.metric==metric)]
    if left:d=d[d.left==left]
    if rights:d=d[d.right.isin(rights)]
    return d.copy()
def effect_table(d,scale=100):
    return pd.DataFrame({'比较':d.left+' − '+d.right,'效应':d.estimate*scale,'95%下限':d.ci95_low*scale,'95%上限':d.ci95_high*scale})

def methods(phase):
    d=read(phase+'_statistics.csv');d=d[(d.view=='overall')&(d.bootstrap=='hierarchical')]
    wide=d.pivot(index=['condition','label'],columns='metric',values='estimate').reset_index()
    counts=d.drop_duplicates(['condition','label'])[['condition','label','success_equivalent','applicable_equivalent','valid_output_equivalent','raw_calls','base_clusters']]
    w=wide.merge(counts,on=['condition','label'])
    t=read('raw_call_latency.csv');t=t[(t.phase==phase)&(t.view=='label')&(t.partition=='all_calls')][['label','p50_ms','p95_ms','p99_ms']]
    return w.merge(t,on='label')

def main():
    assert load(OUT/'review_COMPLETE.json')['passed'] and load(OUT/'statistics_COMPLETE.json')['passed']
    main=methods('P4');csv('MAIN_RESULTS.csv',main)
    display=main[['label','success_equivalent','applicable_equivalent','online_success','U_exec','conditional_U','conditional_N_drop','conditional_M_all','p95_ms','p99_ms','timeout_rate']].copy()
    display.online_success*=100;display.timeout_rate*=100
    display.columns=['方法','成功等价数','分母','在线成功%','U_exec','有效条件效用','有效条件删除数','有效条件移动秒','p95毫秒','p99毫秒','超时%']
    main_effect=effect_table(effects('P4',left='Rule-PALR'));csv('MAIN_PAIRED_EFFECTS.csv',main_effect)
    subgroup=read('P4_effects.csv');subgroup=subgroup[(subgroup.bootstrap=='hierarchical')&(subgroup.left=='Rule-PALR')&(subgroup.right=='Fixed-PALR')&(subgroup.metric=='online_success')&subgroup.view.isin(['layer','kind'])]
    subtable=pd.DataFrame({'分层':subgroup.view+':'+subgroup.stratum,'规则−固定(pp)':subgroup.estimate*100,'95%下限':subgroup.ci95_low*100,'95%上限':subgroup.ci95_high*100})
    mechanisms=methods('mechanisms');upgrades=methods('upgrades');transfer=methods('transfer')
    trajectory=read('trajectory_statistics.csv');trajectory=trajectory[trajectory.bootstrap=='hierarchical']
    trajwide=trajectory.pivot(index='label',columns='metric',values='estimate').reset_index()
    csv('TRAJECTORY_RESULTS.csv',trajwide)
    trajectory_effects=read('trajectory_effects.csv');trajectory_effects=trajectory_effects[(trajectory_effects.bootstrap=='hierarchical')&(trajectory_effects.left=='Rule-PALR')&(trajectory_effects.metric=='delivered_utility')]
    loadtable=read('single_factor_statistics.csv');loadtable=loadtable[(loadtable.view=='overall')&(loadtable.bootstrap=='hierarchical')&(loadtable.label=='Rule-PALR')&loadtable.condition.str.startswith('N|')]
    loadrates=loadtable[loadtable.metric=='online_success'].copy()
    loadrates['N']=loadrates.condition.str.split('|').str[1].astype(float)
    loadrates['成功%']=loadrates.estimate*100;loadrates['95%下限']=loadrates.ci95_low*100;loadrates['95%上限']=loadrates.ci95_high*100
    loadrates=loadrates.merge(loadtable[loadtable.metric=='timeout_rate'][['condition','estimate']].rename(columns={'estimate':'timeout'}),on='condition')
    loadrates['超时%']=loadrates.timeout*100
    cpchange=read('paired_condition_sensitivity.csv');cpchange=cpchange[(cpchange.phase=='references')&(cpchange.bootstrap=='hierarchical')&(cpchange.label=='Rule-PALR')]
    failures=read('failure_review.csv');f=failures[(failures.phase=='P4')&(failures.view=='label')][['label','applicable_calls','online_success_calls','exclusive_timeout','exclusive_not_validated','exclusive_urgent_unserved']]
    counts=load(OUT/'published_table_crosscheck.json');physical=sum(v['raw_replay']['physical_plans_newly_checked'] for v in counts['phases'].values())
    fields=sum(v['raw_replay']['metric_fields_recomputed'] for v in counts['phases'].values())
    selected={}
    for phase in ['P4']+PHASES:
        for example in load(OUT/'raw_audit'/phase/'examples.json'):
            selected.setdefault(example['category'],example)
    case_rows=[]
    for category,example in selected.items():
        row=example['row'];case_rows.append(dict(category=category,phase=example['phase'],base_id=row['base_id'],scenario=row['scenario'],method=row['label'],status=row['status'],total_ms=row['total_ms'],online_success=row['online_success'],errors=row['errors'],source=example['source']))
    assert set(selected)=={'cancellation_success','urgent_failure','window_or_receiver_counterexample'}
    csv('case_review.csv',pd.DataFrame(case_rows))
    (OUT/'CASE_REVIEW.md').write_text('# 可追溯案例复核\n\n选择顺序固定为P4及协议PHASES顺序，各阶段按基实例分片路径排序，取该类别首个原始记录，不按方法优势筛选。\n\n'+md(pd.DataFrame(case_rows))+'\n\n完整输入、输出计划、修改轨迹和校验见raw_audit对应阶段examples.json；超时或紧急未服务不能单独证明物理不可行。\n',encoding='utf-8')
    summary=f'''# P6 最终阶段实验报告

日期：2026-11-18。分析起点：Git `d940b9afc36a7451d92f49fe6929493b1d3a2602`。本阶段完成统计、失败复核和结果归档，不新增性能实验。

## 1. 结论与使用边界

1. 在已交付 P4 默认负载、完整方法调用 50 ms 的测试中，PALR 相对 PUCT-ISL、ALNS-ISL、CP-SAT-50ms 保持更高预算内成功率和更低超时率。三个方法的全后缀搜索域与 PALR 局部域不同；机制判断使用单列的 P5 同邻域比较。
2. 规则控制对固定 PALR、验证择优固定参数没有确立稳定净收益。P4 规则−固定成功率差为 −0.275 pp，分层配对95%区间为[−0.625,+0.0833] pp。跨零不能解释为严格等效，也不能据测试改选参数。
3. 共享50 ms升级没有超过PALR-only。更高负载 N500/N1000 下成功率明显下降、超时上升；全部方法的P4 p99超过50 ms，当前Python合作式截止实现不支持硬实时保证。
4. 连续事件的独立单位为100条完整轨迹；交付效用与静态U_exec分开。轨道层仅两个测试卫星组，迁移子集可能仅一个组；bootstrap无法弥补卫星组数量不足或证明跨时段、全星座外推。

## 2. 范围、取消项与历史来源

用户确认取消中竞争 N500/h0.8 的 P4-M/P5-M；四个相关容器均已停止并移除。删除本地未交付补充目录的命令被自动审批检查拒绝，原因为“blocked by policy”；本地未跟踪残留明确排除，不进入统计、封存或Git提交。P5原已交付的N500/N1000单因素结果仍保留。原P0–P5科学证据保持原字节，本阶段只新增P6材料和更新当前导航。

| 阶段 | 本阶段使用的证据 | 正确性与解释 |
| --- | --- | --- |
| P0 | 实现契约、115项检查、12事件×3方法 | 论文规则重新实现，不宣称原代码精确复现 |
| P1 | 150/150试点、125检查、轨道划分和窗口审计 | 合成需求结合固定轨道快照；不能当真实业务分布 |
| P2 | 200小规模事件、264原生模型历史审计 | 200均OPTIMAL；离散局部域、早期v1实现，不能证明P4/P5全局在线最优 |
| P3/P3-R | 参数/阈值冻结、训练验证记录 | 开发证据，不混入独立测试样本；ET未显示预定净收益 |
| P4 | 1000基实例×12事件、192000主调用 | 400D1/300D2-S/300D2-O；另384000计时调用单列 |
| P5 | 381200调用；消融300、专项100、异常50、CP参考100、轨迹100 | ET/A6按批准不适用；IPC仅来源/解析/适用性审计，没有IPC性能实验 |

逐阶段旧证据入口见上级README和P5 prior_stage_review；完整历史文件对象清单见`historical_git_blobs.json`，本次读取来源SHA256见`source_manifest.json`。

## 3. 统计方法与分母

依完整实验方案§5/§9–13和[P6统计协议](../../../protocol/P6_STATISTICS_V1.md)，每个预先固定的实例集合执行10,000次配对簇bootstrap，PCG64种子20261020。D1重采基实例；D2-S/D2-O先有放回抽卫星组，再分别在抽中组内有放回抽实例。重复抽到同组时分别抽组内实例。所有方法、事件和条件使用同一抽样权重，层权重固定为原子集构成，组大小变化不改变层权重。另列只重采实例、条件于已有卫星组的区间。

随机搜索种子11/23/47/89/131先在同事件内平均；成功数为等价事件数，可能含小数。种子和20次计时重复不增加独立n。方法表同时给基实例数、事件条件数、原始调用数、适用/N-A和有效输出分母。主成功=预算内可行且服务满足；有效输出不要求服务紧急任务。无效/迟到输出U_exec=0；有效条件效用/删除/新增/移动为“有效分子总和÷有效输出总数”。全部失败仍留在主分母。

配对差用同次重采指标之差。双方有效的配对质量另给保守交集：要求该事件双方所有种子均有效，报告实际交集事件数/基实例数。相对Minimal的归一化增益只在双方有效且Minimal效用>0的交集中定义，零基线不补零。零分母重采记未定义并给次数。95%区间为2.5/97.5百分位逐项边际区间；没有新增p值，不作同时覆盖或多比较显著性宣称。统计工作在P4/P5结果已知后完成，不能称作新的预注册。

重采整数计数和归一化规则保存在`resampling/`；每项完整10,000重复保存在`replicates/`，区间以float64计算、重复数组以float32保存。每个文件伴随来源、列名和SHA256。完整分层表含三数据层、扰动、FR/q及P4全部36单元。

## 4. P4 主比较

{md(display)}

搜索方法原始调用为五种子混合：PUCT、ALNS各60000次，主表仍各12000等价事件；其余各12000次。`raw_call_latency.csv`给原始调用均值/p50/p95/p99，以及成功/失败分区；不是“种子平均时延的分位数”。

规则PALR相对各基线的预算内成功率差，单位pp；正值有利于规则：

{md(main_effect)}

规则对固定PALR的分层效应：

{md(subtable)}

以上分层区间不能通过“一个跨零、另一个不跨零”推断交互；完整效用、超时和有效条件质量效应见`P4_effects.csv`。所有方法的成功率和U_exec均有层级/仅实例两种区间，见`P4_statistics.csv`。主比较没有把全局操作域与同邻域机制混为一体。

## 5. P5机制、控制与升级

同邻域、相同操作预算机制的成功率配对差（PALR-local减比较方法，pp）：

{md(effect_table(effects('mechanisms',left='PALR-local')))}

A5规则主线（联合规则减固定w5/B2、验证择优固定w5/B1、仅B、仅w，pp）：

{md(effect_table(effects('ablations',left='Rule-PALR',rights=['Grid-w5-B2','Grid-w5-B1','B-only','w-only'])))}

A1/A2候选资格、A3/B与A4/w网格、A7仅插入与完整算子、A8随机并列与干扰词典序、A10有/无剩余时间特征的全部比较分别入表。PUCT模拟次数敏感性另列`simulations_statistics.csv`。A9逐基实例离线25动作网格单列`A9_offline_statistics.csv`，动作选择使用同一实例全部12事件，是乐观后选择描述上界；bootstrap固定已选动作，不能校正选择乐观性，不能当在线50ms策略。逐事件包络仍只保留为更乐观的补充。

规则相对固定w5/B2的平均执行效用差（原效用单位）：

{md(effect_table(effects('ablations',metric='U_exec',left='Rule-PALR',rights=['Grid-w5-B2']),1))}

共享总预算升级成功率差（pp）：

{md(effect_table(effects('upgrades')))}

升级阈值已在P5预定验证子集内固定，P6没有重新调参。两阶段共用50ms、第一阶段和累计热启动契约沿用P5独立校验；失败不能被解释为物理不可行。

## 6. 敏感性、迁移和连续事件

`single_factor_statistics.csv`按负载N、FR、窗口跨度、背景占用、距离、热点和速率分别报告，包含每个因素水平的适用分母和数据层；不把不同因素拼成新总体排名。配对窗口压力/删窗/收缩及100例CP-SAT参考计划，在各自表中独立比较。`paired_condition_sensitivity.csv`额外给同基实例、同事件的改变条件减原P4条件效应；两次性能测量时段不同，不合并延迟分布或宣称纯实现加速。距离变化可能重生成紧急端点，速率变换仅作用原方案指定任务；需保留P5原定义。

规则PALR的负载边界（各行同100基实例、1200事件；成功区间为轨道组先抽）：

{md(loadrates[['N','success_equivalent','applicable_equivalent','成功%','95%下限','95%上限','超时%']].sort_values('N'))}

规则PALR在CP参考构造下相对原参考的改变（效用原单位，成功率差为比例而非pp）：

{md(cpchange[['metric','estimate','ci95_low','ci95_high','paired_event_conditions','base_clusters']])}

跨星座固定30例OneWeb测试，仅在该子集内比较：

{md(transfer[['label','success_equivalent','applicable_equivalent','online_success','U_exec','timeout_rate']])}

异常50例覆盖40D1+10Starlink，没有OneWeb；冻结取消/冻结窗冲突与配对正常控制单列，不能视为三层对称测试。100个CP参考全部原生OPTIMAL只证明初始参考构造的目标，不证明在线扰动修复全局最优。IPC无完整时序PDDL规划/验证适配器，未运行性能实验；ET/A6不适用。

连续事件按100完整轨迹汇总，不将1000事件视为1000独立轨迹。实际状态随方法演化，比较是配对同一外生事件流的整轨迹处理效果：

{md(trajwide[['label','delivered_utility','completed_tasks','failures','failure_to_success_recoveries','cumulative_active_drops','cumulative_movement','unserved_with_individually_feasible_window']])}

交付效用差（规则减各对照，每轨迹）：

{md(effect_table(trajectory_effects,1))}

窗口错失采用“曾有个体几何可行窗而最终未执行”定义，不是拥塞不可行的证明；完成任务效用只计一次，失败/恢复只用适用事件。具体定义、N/A和末态未服务见P5轨迹原表及本阶段轨迹统计/配对区间表。

## 7. 失败复核与精确参照

573200条原始记录均重算指标、截止、服务、有效输出与U_exec，并按唯一事件/方法/种子键核对已发布逐调用表的12个评分/关键指标字段（清单见`published_table_crosscheck.json`），共重新计算{fields}个原始指标/评分字段。逐原始分片核对SHA256收据。本次新物理检查{physical}个计划：所有未验证输出，以及每个方法/种子/基实例的首个已验证输出；首个已验证输出还重放完整修改轨迹/准入/冻结/邻域外不变契约。此前P4/P5对全部已验证输出的独立检查以原封存清单/源码哈希复用，不能将本次抽查称为再次全量物理重放。

P4互斥失败归因按“超时优先→未验证→紧急未服务”分解，原始调用分母如下（搜索仍为五倍调用数）：

{md(f)}

`failure_review.csv`另保留可重叠超时/未验证/已验证但紧急未服务标签；互斥三项总和必须等于适用调用减成功调用。`solver_statuses.csv`保留UNKNOWN、显式冻结冲突等原状态。超时、UNKNOWN或未服务均不等于已证明物理不可行。

同实际输入上其它方法/种子或迟到已验证输出提供的服务计划，定义“观察到可行见证”子集；`known_feasible_service.csv`和逐ID列表保留分母。该子集不是完整物理可行总体，也不能在不同局部域间声称同域最优。连续轨迹状态不同，不跨方法借用可行见证。取消成功、紧急失败及窗口/接收冲突反例按基实例分片路径排序后取该类首个原始记录，索引见`CASE_REVIEW.md`，完整输入、计划、校验和原始来源见`raw_audit/*/examples.json`；未按PALR优势选例。

P2的200事件均有离散局部OPTIMAL证书，完整词典序匹配数及效用差见`P2_legacy_summary.json`和`P2_exact_gap_legacy.csv`。它属于早期v1实现的正确性参照，不与P4/P5新版在线效用合并；不重跑求解器、不将旧证书扩大到新域。

## 8. 图表、复现与验收

九张图分别呈现主配对成功效应、同邻域机制、A5控制、共享升级、负载边界、轨迹效用、P2局部差距、效用/扰动及配对窗口敏感性。每图有PNG/PDF/SVG、来源CSV、统计说明和PDF字体/碰撞QA；图源见`figures/`与`plot_stage6.py`。原P5八张图仍按封存哈希保留，P6图不替代旧图。

入口：[最终结果摘要](FINAL_RESULTS.md)、[复现指南](REPRODUCE.md)、`final_acceptance.json`、`acceptance_manifest.json`。成功完成本阶段表示所要求的统计与可追溯材料交付完成，不表示规则优越、所有工程指标达到、硬实时成立或IPC性能已完成。P6为本次最后阶段，完成后停止，不继续实验。
'''
    (OUT/'P6_REPORT.md').write_text(summary,encoding='utf-8')
    final='# P0–P6 最终结果摘要\n\n'+summary.split('## 1.')[1].split('## 2.')[0].replace(' 结论与使用边界\n','')+'\n## 默认负载主表\n\n'+md(display)+'\n\n## 配对成功率差（pp）\n\n'+md(main_effect)+'\n\n详细边界、分层、专项、失败见[P6报告](P6_REPORT.md)。复现入口见[指南](REPRODUCE.md)。\n'
    (OUT/'FINAL_RESULTS.md').write_text(final,encoding='utf-8')
    guide='''# P6 复现实验指南

## 证据与环境

从完整Git仓库运行，所有路径相对于仓库根。P4/P5原始分片、输入和原始源码必须保留。P6只做统计与只读复核，不运行新的在线性能实验。环境精确版本见environment.json；需要Python、numpy、pandas、matplotlib、scipy、pytest和可选PyMuPDF。原CP-SAT证书沿用已封存原生审计，不需要主机重装ortools。

建议单线程BLAS，避免统计矩阵并发干扰其它任务。Windows PowerShell：

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONPATH=(Join-Path (Get-Location) 'experiment_runs/scripts')
$env:P6_OUT=(Join-Path (Get-Location) 'experiment_runs/reports/p6/P6-reproduction')
python -m pytest experiment_runs/tests/test_p6_statistics.py -q --junitxml="$env:P6_OUT/qa/unit_tests.xml"
python experiment_runs/scripts/prepare_stage6.py
python experiment_runs/scripts/analyze_stage6.py
python experiment_runs/scripts/sensitivity_stage6.py
python experiment_runs/scripts/oracle_stage6.py
python experiment_runs/scripts/audit_stage6_raw.py
python experiment_runs/scripts/review_stage6.py
python experiment_runs/scripts/plot_stage6.py
python experiment_runs/scripts/report_stage6.py
python experiment_runs/scripts/accept_stage6.py
```

prepare_stage6.py默认要求分析父提交；在交付后的提交上重现时用环境变量P6_ALLOW_DELIVERED=1，仍从固化父提交读取历史对象清单。不要覆盖已有P6封存批次。Linux对应export环境变量并使用同一脚本。

图表可选`--qa-tools <nature-figure审核脚本目录>`生成技能标准的字体/碰撞QA；不提供时仍可完全重画，输出单图对齐N/A记录。本次交付保留真实审核结果和人工图像复核说明。精确字体可能随系统替代改变，数值CSV和抽样计数应完全一致；PDF/PNG/gzip包头/环境及运行时间不要求字节级重现。

新目录中执行accept_stage6.py前，需对新渲染图完成PDF字号/碰撞QA，并写入新的figures/visual_review.json，不能把旧图的视觉审查直接当新图通过。上方命令中的plot_stage6.py若没有传--qa-tools，只完成绘图与数值复现，验收会明确缺少新QA而停止。本交付目录中的九图已经实际完成上述审查。

单因素2,280个独立原始分片可用`python experiment_runs/scripts/parallel_audit_stage6.py`四进程复核；它完整覆盖同一批输入，合并时检查分区无交集、分片2280和调用99840。其它阶段保持顺序复核，或在单因素已生成COMPLETE后运行audit_stage6_raw.py跳过已通过阶段。并行的是只读审计，不是在线方法计时。

## 独立核验

验收脚本校验所有消费来源SHA256、原历史科学文件对象、573200条原始评分/发布表对应、互斥失败归因、10000重采和完整比较范围、P4点估计重建、单位测试、图源和验收清单。重现的统计表按数值比较；完整重复数组为float32存储，百分位区间由float64原值计算。resampling记录整数抽样频数；轨道层按层原样本量归一，避免组大小随机改变层权重。

每个总体/分层/条件都保留适用/有效输出分母及未定义重采次数。只重采实例的区间用于条件敏感性，不替代轨道组先抽的主区间。仅两个测试卫星组及一个组的迁移无法支持广泛轨道组总体推断。A9离线选择结果冻结后仅作乐观描述。

## 取消项

P4-M/P5-M按用户决定排除；相关容器已停止并移除。本地未跟踪残留的删除被自动审批拒绝，不把它们纳入Git或复现依赖。原P5单因素N500/N1000继续保留。
'''
    (OUT/'REPRODUCE.md').write_text(guide,encoding='utf-8')
    save(OUT/'report_COMPLETE.json',dict(passed=True,main_methods=len(main),new_physical_checks=physical,raw_score_fields_recomputed=fields,figure_count=9))

if __name__=='__main__':main()
