"""Audit complete revision evidence, select once, and write an honest report."""
from collections import defaultdict
import csv,gzip,hashlib,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from train_p3r import load,sha
P3=ROOT/'reports/p3/P3-20261110';OUT=ROOT/'reports/p3r/P3R-20261112'
METHODS=('fixed','rule','et_original','puct','alns','action','deviation')

def main():
    complete=load(OUT/'validation/COMPLETE.json');freeze=load(OUT/'validation_freeze.json')
    assert complete['calls']==168000 and complete['freeze_sha256']==sha(OUT/'validation_freeze.json')
    for name,h in freeze['sha256'].items():assert sha(ROOT/name)==h,name
    groups=defaultdict(list);by_base=defaultdict(dict);n=0;files={};layer_bases=defaultdict(set)
    for i,p in enumerate(sorted((OUT/'validation').glob('*.json.gz'))):
        receipt=load(p.with_suffix('.receipt.json'));assert receipt['sha256']==sha(p)
        files[p.relative_to(ROOT).as_posix()]=sha(p)
        with gzip.open(p,'rt') as f:rs=[json.loads(l) for l in f]
        assert len(rs)==168 and receipt['calls']==168
        seen=set()
        for r in rs:
            key=(r['load'],r['scenario'],r['method']);assert key not in seen;seen.add(key)
            result=r['result'];m=result['metrics'];total=result['total_ns'];ontime=total<=50_000_000
            assert m['within_budget']==ontime
            assert abs(m['L_total_ms']-total/1e6)<1e-9
            assert m['online_success']==bool(m['applicable'] and m['service_success'] and ontime)
            assert m['valid_output']==bool(m['applicable'] and m['strict_feasible'] and ontime)
            assert m['U_exec']==(m['U_raw'] if m['valid_output'] else 0)
            if result['validated']:
                assert result['validation']['feasible']
                assert result['admissions_cumulative']<=result['B']
            # Drop large immutable plan/trace evidence after auditing each record.
            # Original sealed shards remain the source of truth.
            r['result']={k:result[k] for k in ('metrics','total_ns','status','timings_ns')}
            for k in ('controller_invoked','controller_fallback'):
                if k in result:r['result'][k]=result[k]
            n+=1;groups[r['load'],r['method']].append(r)
            by_base[r['base_id']][key]=r
            layer_bases[r['layer']].add(r['base_id'])
        if i%100==0:print('P3-R audit bases',i+1,flush=True)
    assert n==168000 and len(by_base)==1000
    summaries=[]
    for (label,method),rs in groups.items():
        cells=defaultdict(list)
        for r in rs:cells[r['layer'],r['scenario']].append(r)
        assert len(cells)==36
        def macro(fn):return float(np.mean([np.mean([fn(r) for r in rows]) for rows in cells.values()]))
        times=[r['result']['total_ns']/1e6 for r in rs]
        control=[r['result']['timings_ns'].get('control_ns',0)/1e6 for r in rs]
        s=dict(load=label,method=method,n=len(rs),macro_online_success=macro(lambda r:r['result']['metrics']['online_success']),
            macro_normalized_U_exec=macro(lambda r:r['result']['metrics']['U_exec']/max(1,r['reference_utility'])),
            macro_drop=macro(lambda r:r['result']['metrics']['N_drop']),macro_add=macro(lambda r:r['result']['metrics']['N_add']),
            macro_movement=macro(lambda r:r['result']['metrics']['M_all']),macro_timeout=macro(lambda r:r['result']['status']=='timeout'),
            timeouts=sum(r['result']['status']=='timeout' for r in rs),p50_ms=float(np.percentile(times,50)),p95_ms=float(np.percentile(times,95)),
            p99_ms=float(np.percentile(times,99)),control_p95_ms=float(np.percentile(control,95)),
            call_wall_p95_ms=float(np.percentile([r['call_wall_ns']/1e6 for r in rs],95)),
            controller_invocations=sum(r['result'].get('controller_invoked',False) for r in rs),
            actual_rule_deviations=sum(not r['result'].get('controller_fallback',True) for r in rs))
        for kind in ('cancellation','urgent_insertion','reward_update'):
            relevant=[rows for (_,scenario),rows in cells.items() if rows[0]['kind']==kind]
            s[kind+'_online_success']=float(np.mean([np.mean([r['result']['metrics']['online_success'] for r in rows]) for rows in relevant]))
        summaries.append(s)
    summaries.sort(key=lambda s:(s['load'],METHODS.index(s['method'])))
    index={(s['load'],s['method']):s for s in summaries};selected={};paired={}
    for label in ('default','N500-h0.8'):
        rule=index[label,'rule'];eligible=[]
        for mode in ('action','deviation'):
            s=index[label,mode];gain=s['macro_online_success']-rule['macro_online_success']
            s['success_gain_vs_rule']=gain
            s['eligible_main_controller']=bool(gain>=.005 and s['control_p95_ms']<=3 and s['macro_timeout']-rule['macro_timeout']<=.005)
            if s['eligible_main_controller']:eligible.append(s)
            diffs={}
            for layer,ids in layer_bases.items():
                diffs[layer]=np.asarray([np.mean([int(by_base[id][label,j,mode]['result']['metrics']['online_success'])-
                   int(by_base[id][label,j,'rule']['result']['metrics']['online_success']) for j in range(12)]) for id in sorted(ids)])
            rng=np.random.Generator(np.random.PCG64(20261112));boots=[]
            for _ in range(2000):boots.append(np.mean([rng.choice(v,len(v),replace=True).mean() for v in diffs.values()]))
            paired[label+'/'+mode]=dict(macro_paired_gain=gain,stratified_base_bootstrap_95_interval=np.percentile(boots,[2.5,97.5]).tolist(),
                resamples=2000,independent_bases=1000,note='development validation comparison; no independent test claim')
        best=min(eligible,key=lambda s:(-s['macro_online_success'],-s['macro_normalized_U_exec'],s['macro_drop'],s['macro_add'],s['macro_movement'],s['p95_ms'],METHODS.index(s['method']))) if eligible else rule
        selected[label]=dict(main_controller=best['method'],reason='predeclared net-benefit gates passed' if eligible else 'neither sparse candidate passed all predeclared net-benefit gates')
    # Frozen P3 acceptance files must all retain their exact content.
    old_manifest=load(P3/'acceptance_manifest.json');old_verified=0
    for rel,h in old_manifest['file_sha256'].items():
        p=ROOT.parent/rel
        assert sha(p)==h,('frozen P3 changed',rel)
        old_verified+=1
    audit=dict(passed=True,records=n,validation_bases=1000,receipts=len(files),frozen_P3_files_verified=old_verified,
       independent_replay='original isl.validation was run on every validated output by the collector before sealing each receipt',
       source_freeze_verified=True,test_instances=0,P4_started=False,selected=selected)
    (OUT/'final_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    (OUT/'selected_controllers.json').write_text(json.dumps(selected,indent=2)+'\n')
    (OUT/'paired_comparisons.json').write_text(json.dumps(paired,indent=2)+'\n')
    (OUT/'validation_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    fields=list(dict.fromkeys(k for s in summaries for k in s))
    with (OUT/'validation_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(summaries)
    train=load(OUT/'models/index.json');runtime_gate=load(OUT/'training_gate_linux.json');control_gate=load(OUT/'controller_training_gate.json')
    text=['# P3-R 运行时修订与控制器精简补充实验报告','',
       '原 P3 保持冻结。本实验使用相同训练与验证输入，是已使用验证集上的开发补充实验，不是独立测试。未进入 P4。',
       '',f'完成 {n:,} 次修订验证：1000 基实例 × 2 负载 × 12 情景 × 7 方法。全部失败和超时保留；每条已验证输出均经原始独立校验器离线回放。',
       '', '## 固定协议与训练成本','',
       '诊断训练集为三数据层各前20基实例。共享优化只改变校验器冲突枚举与精确项索引，保留完整最终校验、原规则、原六头ET和原修复算子。两个精简候选共用四动作、32棵深度6的ExtraTrees；复用80000旧标签并按预算新增2400中竞争训练记录。全部模型、门控、选择阈值在修订验证前哈希冻结。',
       '', '冻结门控为紧急直接插入失败或局部可行候选数≥3，且至少剩余35ms。动作分类器预测四动作或保留规则；偏离分类器只在有训练证据优于规则时偏离。紧急动作集均为正预算；规则回退未服务紧急任务不计成功。',
       '', '## 验证结果','',
       '|负载|方法|宏在线成功率|取消|紧急|奖励|p95 ms|超时次数|控制p95 ms|',
       '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for s in summaries:text.append('|'+ '|'.join([s['load'],s['method']]+[f'{100*s[k]:.2f}%' for k in ('macro_online_success','cancellation_online_success','urgent_insertion_online_success','reward_update_online_success')]+[f"{s['p95_ms']:.3f}",str(s['timeouts']),f"{s['control_p95_ms']:.3f}"] )+'|')
    text += ['', '## 训练计时与成本','',
      f"新增标签内核响应累计 {train['costs']['new_label_response_ns']/1e9:.3f} s，新增特征提取累计 {train['costs']['new_feature_ns']/1e9:.3f} s。模型训练及保存：动作 {train['files']['action']['fit_and_save_ns']/1e9:.3f} s、偏离 {train['files']['deviation']['fit_and_save_ns']/1e9:.3f} s；文件大小分别 {train['files']['action']['bytes']:,} 与 {train['files']['deviation']['bytes']:,} 字节。4600个训练状态来自4000个独立基实例，新增中竞争配对状态不计作独立样本。",
      '', '|训练负载/配置|旧版超时/720|修订超时/720|旧p95 ms|修订p95 ms|修订基础p99 ms|',
      '|---|---:|---:|---:|---:|---:|']
    for label in ('default','N500-h0.8'):
        for B in (0,2):
            a=runtime_gate['groups'][f'old/{label}/B{B}'];b=runtime_gate['groups'][f'revised/{label}/B{B}']
            text.append(f"|{label}/B{B}|{a['timeouts']}|{b['timeouts']}|{a['response_p50_p95_p99_ms'][1]:.3f}|{b['response_p50_p95_p99_ms'][1]:.3f}|{b['baseline_p99_ms']:.3f}|")
    text += ['', '基础p99在训练诊断中仍未达到15ms目标；这是未达目标，不能称为全部训练门禁通过。无截止行为等价检查288例，专项差分/门控测试24项通过。最初含剖析的诊断、第一轮Linux计时与Windows开发计时均独立保留。',
       '', '|训练控制组合|含特征控制p95 ms|推理调用/720|端到端超时/720|', '|---|---:|---:|---:|']
    for key,g in control_gate['groups'].items():text.append(f"|{key}|{g['control_p95_ms']:.3f}|{g['invoked']}|{g['timeouts']}|")
    text += ['', '## 一次性部署选择','']
    for label,choice in selected.items():text.append(f"- {label}：主控制器 **{choice['main_controller']}**；{choice['reason']}。")
    text += ['', '学习候选必须同时满足：相对修订规则宏在线成功率至少提高0.5个百分点、含特征的控制p95≤3ms、宏超时率增加≤0.5个百分点。未达标的ET保留为消融负结果，不追加调参。',
       '', '## 解释边界','',
       '训练共享基础p99≤15ms、中竞争超时率<5%是工程目标，不是严格实时保证；实际达标状态见训练门禁和本报告超时统计。固定PALR沿用原P3的分负载参数，中竞争B=0不能证明紧急修复能力。',
       '', '响应计时沿用P3边界：完整最终校验计入，结果指标计算与JSON证据序列化发生在内核响应时间戳之后。另存call_wall_p95_ms显示整个Python调用开销，不能把其与内核响应时间混用。控制包装器使用精确外包时钟，包含派发至修复内核的开销。',
       '', '历史P3和修订版在不同测量时段执行，不能把所有差异单独归因于代码；同一训练集上的旧版/修订版乱序配对计时用于隔离共享优化。基实例为不确定性分析的独立单位，负载和情景保持配对；置信区间为三数据层内基实例自助法2000次。',
       '', '门控推理调用比例与真正偏离规则次数见validation_summary.json；若比例并非少数，不能声称已实现稀疏调用。没有精确可行性证书的失败不标为物理不可行。',
       '', '## 审计','',json.dumps(audit,ensure_ascii=False,indent=2),'']
    report='\n'.join(text)
    addendum=OUT/'report_interpretation.md'
    if addendum.exists():report += '\n'+addendum.read_text(encoding='utf-8')
    (OUT/'P3R_REPORT.md').write_text(report,encoding='utf-8')
    # Pipeline log/receipt completion occurs after finalization; do not hash live logs.
    paths=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name!='acceptance_manifest.json' and 'pipeline' not in p.relative_to(OUT).parts)
    manifest={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    extra=list((ROOT/'src/isl/p3r').glob('*.py'))+list((ROOT/'scripts').glob('*p3r*.py'))+list((ROOT/'tests').glob('test_p3r*.py'))+[ROOT/'protocol/P3R_EXECUTION_V1.md']
    manifest.update({p.relative_to(ROOT).as_posix():sha(p) for p in extra})
    (OUT/'acceptance_manifest.json').write_text(json.dumps(dict(passed=True,files=manifest),indent=2)+'\n')
    print(json.dumps(audit),flush=True)
if __name__=='__main__':main()
