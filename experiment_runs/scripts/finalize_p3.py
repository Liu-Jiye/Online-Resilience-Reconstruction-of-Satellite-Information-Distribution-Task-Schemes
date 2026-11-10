"""Finalize P3 only after all required computation and scoring audits pass."""
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent;run=ROOT/'reports/p3/P3-20261110'


def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    audit=load(run/'final_audit.json');assert audit['passed'] and audit['total_records']==992000
    inputs=load(run/'input_summary.json');model=load(run/'models/index.json');calibration=load(run/'et_calibration.json')
    grid=load(run/'grid_summary.json');rules=load(run/'rules_summary.json');et=load(run/'et_summary.json');search=load(run/'search_summary.json')
    cfg=load(ROOT/'configs/p3_v1.json');parameters={}
    for label in cfg['loads']:
        fixed=grid['selected'][label];rule=rules['selected'][label];learned=et['selected'][label]
        parameters[label]=dict(fixed=dict(w=fixed['setting'][0],B=fixed['setting'][1]),
            rule=next(r for r in cfg['rule_candidates'] if r['name']==rule['setting']),
            ET=dict(probability=learned['setting'][0],time_safety_ratio=learned['setting'][1]),
            PUCT=dict(temperature=search['selected_puct'][label]['setting'][1],simulations=40,max_depth=12,top_k=20,c=1.5),
            ALNS=cfg['ALNS'],search_seeds=cfg['search_seeds'])
    frozen=dict(stage='P3',parameters=parameters,model_files=model['files'],runtime_version='0.3.3-p3-indexed-v2',
                test_instances=0,P4_started=False,rule_adjustment_rounds=1,selection='validation_macro_3layers_x12scenarios_perload',
                source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    (run/'frozen_parameters.json').write_text(json.dumps(frozen,indent=2)+'\n')
    lines=['# P3 阶段报告：参数验证与可选控制器训练','',
        'P3 已完成；仅使用训练与验证数据，未启动 P4、未生成或评估测试实例。结论限于选参与开发阶段，不作为独立测试性能结论。',
        '', '## 范围、环境与追溯','',
        '共4000训练、1000验证基场景：D1为1600/400，D2-S和D2-O各1200/300。每场景有默认自然层与冻结的N500/h0.8中竞争配对层；两者共享场景，不计作10000个独立样本。验证每场景全部12情景（三扰动×FR0/0.6×q0.2/0.8），没有按方法表现补样。',
        '', '固定网格w五值×B五值，实际为25配置，共600000次；此前30配置/720000的算术误记已在P3_GRID_ARITHMETIC_CORRECTION.md公开更正，参数集合未变。规则72000次、ET阈值144000次、搜索96000次、训练标签80000条，正式方法记录合计992000条。',
        '', 'Linux/Python3.11.18，Debian Bookworm容器，单CPU亲和性[0]，数学库线程1；实际Docker VM内存约15.4GiB。完整依赖锁、镜像ID和操作系统包清单已归档。其环境与建议Ubuntu22.04/32GB有差异，后续正式比较须沿用本冻结环境或公开重测。',
        '', '原v2重复校验前缀导致训练预检大量超时。经用户确认增加P3专用等价索引实现0.3.3，保留旧源码和全部预检。72个实际训练情景非截止回放、400组异常校验器对照与237项完整回归通过。资源索引/特征/推理/控制/修复/最终完整校验均按各方法实际发生计入50ms；离线模型加载、文件IO与参考计划构建另列。全部超时保留，不能将离线通过回放当作在线成功。',
        '', '轨道沿用P1一次下载快照与32星组，训练/验证/测试对象384/128/128互斥。P3没有重新下载轨道，没有发布原始GP。原来源与许可登记按哈希引用；原始GP未发现明确再分发许可，发布包只含派生离散接触及合成需求/日历。10000参考计划全部与独立位集贪心一致，120000事件独立复现，输入哈希和分组核验通过。',
        '', '## 分布与负载','',
        '| 划分 | 数据层 | 负载 | 场景数 | 平均参考项数 | 参考终端占用率 |',
        '|---|---|---|---:|---:|---:|']
    for c in inputs['cells']:
        lines.append(f"| {c['split']} | {c['layer']} | {c['load']} | {c['bases']} | {c['reference_count']['mean']:.2f} | {c['scheduled_occupancy']['mean']:.4f} |")
    lines+=['','这些占用率是全时域平均，不等于局部竞争强度。中竞争层沿用先前负载试点预先冻结的N500/h0.8，不据本轮方法结果重新选负载。','',
        '## 冻结参数与验证结果','',
        '按3数据层×12情景等权宏平均，在线成功优先，再比执行效用/事件后参考效用、删除、新增、移动、p95与预定配置顺序。非适用单列，失败与超时不删除；紧急未服务不能靠其他效用抵消。各负载分别选参。','',
        '| 负载 | 方法/配置 | 宏平均在线成功 | 归一执行效用 | 删除 | 新增 | p95 ms | 超时/调用 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    table_rows=[]
    for label in cfg['loads']:
        configs=[('验证择优固定',grid['selected'][label]),('规则',rules['selected'][label]),('ET',et['selected'][label]),
                 ('PUCT',search['selected_puct'][label])]+[('ALNS',r) for r in search['configurations'] if r['load']==label and r['setting'][0]=='ALNS']
        for name,r in configs:
            lines.append(f"| {label} | {name} {r['setting']} | {r['macro_online_success']:.4f} | {r['macro_normalized_U_exec']:.4f} | {r['macro_drop']:.3f} | {r['macro_add']:.3f} | {r['latency_percentiles_ns'][1]/1e6:.2f} | {r['timeouts']}/{r['calls']} |")
            table_rows.append(dict(load=label,method=name,setting=json.dumps(r['setting']),**{k:r[k] for k in ('macro_online_success','macro_normalized_U_exec','macro_drop','macro_add','macro_move','timeouts','calls')},p95_ms=r['latency_percentiles_ns'][1]/1e6))
    lines+=['','规则仅在事先限定三候选中进行这一轮验证选择；未看验证后增加候选。ET六组概率/时延阈值分别冻结，同一个模型在中竞争层的配置经过分层验证，不称零样本选择。完整配置曲线和逐情景分母见grid/rules/et/search_summary.json。',
        '', '## ET模型、成本与校准','',
        '仅默认层4000训练基实例，每实例一个预先平衡情景×20动作，80000条记录全部保留且同基实例不跨划分。成功标签为严格在线成功；五数值头为原始效用增量、删除、新增、移动和方法总时延。ExtraTrees每头200树、深度12、叶最少5、max_features1.0、种子20261020、n_jobs1；成功分类器仅训练时balanced。',
        '', f"训练标签成功/失败计数（顺序失败、成功）：{model['success_labels']}。累计方法响应标注成本{model['label_response_ns']/1e9:.2f}s；离线特征提取成本{model['feature_extraction_ns']/1e9:.2f}s；模型拟合及序列化总成本{model['total_training_wall_ns']/1e9:.2f}s。以上不是整条流水线的墙钟时间，完整日志另存。",'',
        '| 模型文件 | 字节 | SHA256 |','|---|---:|---|']
    for name,r in model['files'].items():lines.append(f"| {name} | {r['bytes']} | {r['sha256']} |")
    lines+=['','校准审计使用全部验证网格20个正预算动作，不拟合新校准器。成功概率阈值过滤后，按预测效用/删除/新增/移动选动作；全部不满足回退规则。真实输出依然接受硬约束检查。','',
            '| 分层 | 记录数 | Brier | ECE10 |','|---|---:|---:|---:|']
    for name,r in calibration['groups'].items():lines.append(f"| {name} | {r['n']} | {r['brier']:.6f} | {r['ECE10']:.6f} |")
    lines+=['','若ET未优于规则/固定，或其推理开销导致失败，须按表保留负结果，不将控制器名称作为独立贡献证据。验证集用于选参，其差异不作为无偏测试增益。','',
        '## 搜索语义与贡献边界','',
        'PUCT是全可编辑后缀的ISL适配实现，40模拟/深度12/top-k20/c1.5/50ms，密度标准化只用4000默认训练实例任务；温度只在0.5/1/2中选择。ALNS使用alns7.0框架，三移除×三修复、每次移除ceil(0.1*m)上限10、200迭代/50ms；按20迭代分段轮盘，反应0.8，奖励5/2/0，严格词典序改善接受。只有种子11执行本轮验证，后续种子11/23/47/89/131冻结，不声称已全执行。',
        '', '两类搜索同样检查冻结、日历、双方终端和累计B5，实际完成模拟/深度/迭代逐条记录。其全后缀自由度大于PALR局部邻域，P3仅选参与核验，不能据该表宣称同邻域公平性能优势；后续机制比较按方案另做。所有实现均非历史论文原代码复现。',
        '', '贡献定位保持“快速完成轻量局部修复，并明确何时需要更强搜索”。本轮不新增在线升级策略，也不拿事后精确答案作触发器。P2-C的多项释放和邻域外阻塞证据仍需独立报告，不能用本轮自然验证代替。',
        '', '## 验收与产物','',
        f"全部{audit['total_records']}条记录通过哈希、预算、执行效用、在线成功和时间边界核验；生成时每条已验证输出均用原独立校验器回放，最终另按预设种子抽查10000条。模型哈希通过；所有正式记录及完整源码、镜像、输入和参数冻结均可追溯。",'',
        '冻结参数：reports/p3/P3-20261110/frozen_parameters.json。输入与逐调用证据、超时、所有配置汇总及阶段日志位于同一run目录。P0/P1/P2冻结证据不覆盖；后续只能由用户启动下一阶段。','']
    report='\n'.join(lines)
    (ROOT/'reports/P3_REPORT.md').write_text(report,encoding='utf-8')
    with (run/'selected_validation_results.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(table_rows[0]));writer.writeheader();writer.writerows(table_rows)
    # Evidence manifest excludes itself and large per-call records already have
    # per-shard SHA receipts; include all those receipts in the acceptance index.
    files=[ROOT/'reports/P3_REPORT.md',ROOT/'configs/p3_v1.json']+list((ROOT/'protocol').glob('P3*.md'))
    files+=list((ROOT/'environment/p3').glob('*'))+list((ROOT/'src/isl/p3').glob('*.py'))+list((ROOT/'scripts').glob('*p3*.py'))
    files+=list(run.glob('*.json'))+list(run.glob('*.csv'))+list((run/'models').glob('*'))
    files+=[run/'data/manifest.json',run/'data/generation_sources.json']
    for mode in expected_modes:files+=list((run/mode).glob('*.receipt.json'))+[run/mode/'source_freeze.json',run/mode/'COMPLETE.json']
    evidence={str(p.relative_to(REPO)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files)) if p.is_file()}
    receipt=dict(stage='P3',passed=True,source_commit=frozen['source_commit'],file_sha256=evidence,final_audit_sha256=hashlib.sha256((run/'final_audit.json').read_bytes()).hexdigest())
    (run/'acceptance_manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (ROOT/'p3_status.json').write_text(json.dumps(dict(stage='P3',status='complete',run_id='P3-20261110',test_instances=0,P4_started=False,report='experiment_runs/reports/P3_REPORT.md'),indent=2)+'\n')
    outputs=REPO.parent.parent/'outputs';outputs.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'reports/P3_REPORT.md',outputs/'P3_REPORT.md')
    for name in ('frozen_parameters.json','final_audit.json','selected_validation_results.csv','et_calibration.json','input_summary.json','acceptance_manifest.json'):
        shutil.copy2(run/name,outputs/('P3_'+name))
    print('P3 complete; report and acceptance exported',flush=True)


expected_modes=('labels','grid','rules','et','search')
if __name__=='__main__':main()
