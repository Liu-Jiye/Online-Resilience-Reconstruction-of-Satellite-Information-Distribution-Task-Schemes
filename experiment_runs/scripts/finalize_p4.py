"""Rebuild P4 tables from complete raw evidence; public independent verification."""
import csv,gzip,json,zipfile
from collections import Counter,defaultdict
import numpy as np
from p4_common import *
from isl.models import canonical_json,case_from_dict,frozen_count,Item
from isl.events import generate_event
from isl.validation import validate
from dataclasses import asdict
from train_p3r import replay

FIELDS=['applicable','strict_feasible','service_success','online_success','valid_output','U_exec','N_drop','N_add','N_sym','M_all','M_edit','D_drop','D_add','M_norm']
def csvwrite(path,rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def stats(rows):
    a=[r for r in rows if r['applicable']];n=len(a)
    d=dict(events=len(rows),applicable=n,na=len(rows)-n)
    for k in FIELDS[1:]:d[k]=float(np.mean([r[k] for r in a])) if n else None
    urgent=[r for r in a if r['kind']=='urgent_insertion']
    d['urgent_events']=len(urgent);d['strict_urgent_success']=float(np.mean([r['service_success'] for r in urgent])) if urgent else None
    d['timeout_rate']=float(np.mean([r['timeout'] for r in a])) if n else None
    return d
def main():
    frozen=load(OUT/'test_freeze.json')
    for p,h in frozen['sha256'].items():assert sha(ROOT/p)==h,('source changed',p)
    manifest=load(OUT/'data/manifest.json');assert len(manifest['instances'])==1000
    assert Counter(r['layer'] for r in manifest['instances'])==dict(D1=400,**{'D2-S':300,'D2-O':300})
    for p,h in manifest['source_sha256'].items():assert sha(ROOT/p)==h
    summary=[];times=defaultdict(list);jitter=defaultdict(list);outcome_times=defaultdict(list);components=defaultdict(list);seed_counts=defaultdict(Counter);seed_groups=defaultdict(list);main_counts=Counter();timing_counts=Counter();hashes={}
    event_path=OUT/'per_event_results.csv';file=None
    try:
        file=event_path.open('w',newline='',encoding='utf-8-sig');writer=None
        for phase,expected in [('main',192000),('timing',384000)]:
            assert load(OUT/phase/'COMPLETE.json')['calls']==expected
            for bi,row in enumerate(manifest['instances']):
                receipt=OUT/phase/(row['id']+'.receipt.json')
                if phase=='timing' and row['id'] not in set(load(OUT/'data/timing_subset.json')['base_ids']):continue
                path=OUT/phase/(row['id']+'.json.gz');assert sha(path)==load(receipt)['sha256']
                assert load(receipt)['freeze_sha256']==sha(OUT/'test_freeze.json')
                hashes[path.relative_to(ROOT).as_posix()]=sha(path)
                archive=OUT/'data'/(row['id']+'.zip');assert sha(archive)==row['archive_sha256']
                with zipfile.ZipFile(archive) as z:
                    payload=z.read('default.json');assert __import__('hashlib').sha256(payload).hexdigest()==row['payload_sha256'];d=json.loads(payload)
                cs=[]
                for e in d['events']:
                    c=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],frozen_count=frozen_count(d['reference'],e['FR'])))
                    assert asdict(generate_event(c.base,c.reference,c.event.kind,e['FR'],e['q'],c.event.seed))==e['event'] or canonical_json(asdict(generate_event(c.base,c.reference,c.event.kind,e['FR'],e['q'],c.event.seed)))==canonical_json(e['event'])
                    cs.append(c)
                seen=set()
                with gzip.open(path,'rt') as f:
                    for line in f:
                        r=json.loads(line);result=r['result'];m=result['metrics'];c=cs[r['scenario']]
                        key=(r['scenario'],r['method'],r['search_seed'],r['repeat']);assert key not in seen;seen.add(key)
                        assert r['input_sha256']==row['payload_sha256'] and r['phase']==phase
                        assert r['method'] in METHODS and result['budget_ms']==50
                        assert r['search_seed'] in (SEEDS if r['method'] in ('PUCT-ISL','ALNS-ISL') else [11])
                        assert result['admissions_cumulative']<=5
                        if result['total_ns']>50_000_000:assert not m['online_success'] and m['U_exec']==0
                        replay(c,result)
                        feasible=bool(result['validated'] and result['validation']['feasible'])
                        service=feasible and (c.event.urgent is None or any(p['task_id']==c.event.urgent.id for p in result['plan']))
                        assert m['strict_feasible']==feasible and m['service_success']==service
                        assert m['online_success']==bool(c.event.applicable and service and result['total_ns']<=50_000_000)
                        counts=main_counts if phase=='main' else timing_counts;counts[r['method']]+=1
                        times[(phase,r['method'])].append(result['total_ns']/1e6)
                        outcome_times[(phase,r['method'],bool(m['online_success']))].append(result['total_ns']/1e6)
                        if phase=='timing':jitter[(row['id'],r['scenario'],r['method'],r['search_seed'])].append(result['total_ns']/1e6)
                        if phase=='main':
                            sc=seed_counts[r['method'],r['search_seed']];sc['calls']+=1;sc['applicable']+=m['applicable'];sc['online_success']+=m['online_success'];sc['timeouts']+=result['total_ns']>50_000_000
                            for name,value in result.get('timings_ns',{}).items():components[r['method'],name].append(value/1e6)
                            components[r['method'],'return_and_dispatch_overhead_ns'].append((result['total_ns']-result['kernel_total_ns'])/1e6)
                            if r['method']=='CP-SAT-50ms':
                                components[r['method'],'model_construction_ns'].append(sum(p['model_construction_ns'] for p in result['phases'])/1e6)
                                components[r['method'],'solver_ns'].append(sum(p['solver_wall_s'] for p in result['phases'])*1000)
                            flat=dict(base_id=row['id'],layer=row['layer'],scenario=r['scenario'],kind=r['kind'],FR=r['FR'],q=r['q'],method=r['method'],search_seed=r['search_seed'],status=result['status'],w=result.get('w'),B=result['B'],admissions_cumulative=result['admissions_cumulative'],total_ms=result['total_ns']/1e6,kernel_ms=result['kernel_total_ns']/1e6,U_raw=m['U_raw'],**{k:m[k] for k in FIELDS})
                            if writer is None:writer=csv.DictWriter(file,fieldnames=list(flat));writer.writeheader()
                            writer.writerow(flat)
                            compact=dict(base_id=row['id'],layer=row['layer'],scenario=r['scenario'],kind=r['kind'],method=r['method'],U_raw=m['U_raw'],timeout=float(result['total_ns']>50_000_000),**{k:float(m[k]) for k in FIELDS})
                            seed_groups[(row['id'],r['scenario'],r['method'])].append(compact)
                assert len(seen)==(192 if phase=='main' else 3840)
                if bi%25==0:print(json.dumps(dict(audit_phase=phase,base_index=bi+1)),flush=True)
            assert sum((main_counts if phase=='main' else timing_counts).values())==expected
    finally:
        if file:file.close()
    events=[]
    for key,rs in seed_groups.items():
        first=dict(rs[0]);assert len(rs)==(5 if first['method'] in ('PUCT-ISL','ALNS-ISL') else 1)
        for k in FIELDS+['timeout','U_raw']:first[k]=float(np.mean([r[k] for r in rs]))
        events.append(first)
    minimal={(r['base_id'],r['scenario']):r for r in events if r['method']=='Minimal-Repair'}
    for r in events:
        u=minimal[r['base_id'],r['scenario']]['U_raw'];r['U_min']=u
        r['delta_U_raw']=r['U_raw']-u;r['normalized_delta_U_raw']=(r['U_raw']-u)/max(1,u)
        r['normalized_U_exec']=r['U_exec']/max(1,u)
    csvwrite(OUT/'seed_averaged_events.csv',events)
    main_table=[];strata=[]
    for method in METHODS:
        rows=[r for r in events if r['method']==method];s=stats(rows)
        s=dict(method=method,**s)
        cells=defaultdict(list)
        for r in rows:cells[r['layer'],r['scenario']].append(r['online_success'])
        s['macro_36cell_online_success']=float(np.mean([np.mean(v) for v in cells.values()]))
        s['success_equivalent_numerator']=sum(r['online_success'] for r in rows if r['applicable'])
        for phase in ('main','timing'):
            arr=np.array(times[phase,method]);s.update({phase+'_p'+str(q)+'_ms':float(np.percentile(arr,q)) for q in (50,95,99)})
            s[phase+'_mean_ms']=float(np.mean(arr))
        for success in (True,False):
            arr=outcome_times['main',method,success];label='success' if success else 'failure'
            s[label+'_calls']=len(arr);s[label+'_p95_ms']=float(np.percentile(arr,95)) if arr else None
        s['normalized_U_exec_mean']=float(np.mean([r['normalized_U_exec'] for r in rows]))
        main_table.append(s)
        for col in ('layer','kind'):
            for value in sorted({r[col] for r in rows}):strata.append(dict(method=method,group=col,value=value,**stats([r for r in rows if r[col]==value])))
    csvwrite(OUT/'main_table.csv',main_table);csvwrite(OUT/'stratified_table.csv',strata)
    csvwrite(OUT/'search_seed_counts.csv',[dict(method=m,seed=s,**v) for (m,s),v in seed_counts.items()])
    csvwrite(OUT/'timing_components.csv',[dict(method=m,component=k,calls=len(v),mean_ms=float(np.mean(v)),p95_ms=float(np.percentile(v,95))) for (m,k),v in components.items()])
    save(OUT/'main_table.json',main_table)
    # Seed means within event, then 12-event means within base; strata resampled intact.
    bybase=defaultdict(list)
    for r in events:bybase[r['method'],r['layer'],r['base_id']].append(r['online_success'])
    layers=['D1','D2-S','D2-O'];arrays={}
    for method in METHODS:
        arrays[method]={layer:np.array([np.mean(v) for (m,l,b),v in sorted(bybase.items()) if m==method and l==layer]) for layer in layers}
    rng=np.random.Generator(np.random.PCG64(20261020));boot={m:[] for m in METHODS};diff={m:[] for m in METHODS if m!='Rule-PALR'}
    groups={}
    for layer in layers:
        rs=sorted([r for r in manifest['instances'] if r['layer']==layer],key=lambda r:r['id'])
        groups[layer]={g:np.array([i for i,r in enumerate(rs) if r['geometry'].get('group')==g]) for g in sorted({r['geometry'].get('group','D1') for r in rs})} if layer!='D1' else {}
    baseboot={m:[] for m in METHODS}
    for _ in range(10000):
        sampled={l:rng.integers(0,len(arrays['Rule-PALR'][l]),len(arrays['Rule-PALR'][l])) for l in layers}
        for m in METHODS:baseboot[m].append(sum(float(np.mean(arrays[m][l][sampled[l]]))*len(sampled[l])/1000 for l in layers))
        for l in layers[1:]:
            names=list(groups[l]);selected=rng.integers(0,len(names),len(names));parts=[]
            for k in selected:
                ids=groups[l][names[k]];parts.append(rng.choice(ids,len(ids),replace=True))
            sampled[l]=np.concatenate(parts)
        vals={m:sum(float(np.mean(arrays[m][l][sampled[l]]))*len(sampled[l])/1000 for l in layers) for m in METHODS}
        for m in METHODS:boot[m].append(vals[m])
        for m in diff:diff[m].append(vals[m]-vals['Rule-PALR'])
    intervals={m:dict(success_ci95=np.percentile(boot[m],[2.5,97.5]).tolist(),base_cluster_only_success_ci95=np.percentile(baseboot[m],[2.5,97.5]).tolist(),difference_vs_rule_ci95=np.percentile(diff[m],[2.5,97.5]).tolist() if m in diff else [0.,0.]) for m in METHODS}
    save(OUT/'cluster_bootstrap.json',dict(seed=20261020,repetitions=10000,independent_base_clusters=1000,method='stratified hierarchical paired bootstrap; orbit groups then bases; seeds averaged within event',orbit_test_groups={l:list(groups[l]) for l in layers[1:]},results=intervals))
    timing=[]
    for m in METHODS:
        a=np.array(times['timing',m]);repeats=[v for (b,sc,method,sd),v in jitter.items() if method==m];assert all(len(v)==20 for v in repeats)
        timing.append(dict(method=m,calls=len(a),p50_ms=float(np.percentile(a,50)),p95_ms=float(np.percentile(a,95)),p99_ms=float(np.percentile(a,99)),pooled_std_ms=float(np.std(a)),pooled_iqr_ms=float(np.percentile(a,75)-np.percentile(a,25)),within_event_std_median_ms=float(np.median([np.std(v,ddof=1) for v in repeats])),within_event_std_p95_ms=float(np.percentile([np.std(v,ddof=1) for v in repeats],95)),within_event_iqr_median_ms=float(np.median([np.percentile(v,75)-np.percentile(v,25) for v in repeats])),timeout_rate=float(np.mean(a>50))))
    csvwrite(OUT/'timing_table.csv',timing)
    save(OUT/'final_audit.json',dict(passed=True,bases=1000,events=12000,main_calls=sum(main_counts.values()),timing_calls=sum(timing_counts.values()),main_counts=main_counts,timing_counts=timing_counts,all_validated_outputs_independently_replayed=True,test_source_unchanged=True))
    lines=['# P4 主测试阶段报告','', '仅执行P4；默认自然负载、八项基线。未运行可选ET、中竞争扩展、P5/P6。', '', '1000测试基实例（400 D1、300 D2-S、300 D2-O）×12事件=12000；主测试192000调用、计时子集100基实例×20重复共384000调用。PUCT/ALNS五种子11/23/47/89/131先在事件内平均；不取最好、不增加独立样本数。','', '完整方法调用50ms包含最终校验、指标及返回对象构造，独立离线重放不能挽救超时。P3-R内核计时保留但不混用。测试前冻结源码/参数/输入，训练输入每方法/种子20预热。','', '| 方法 | 成功率 | 严格可行率 | 紧急服务率（含迟到） | 主调用p95 ms | 超时率 |','|---|---:|---:|---:|---:|---:|']
    for s in main_table:lines.append(f"| {s['method']} | {s['online_success']:.2%} | {s['strict_feasible']:.2%} | {s['strict_urgent_success']:.2%} | {s['main_p95_ms']:.3f} | {s['timeout_rate']:.2%} |")
    lines+=['','成功率分母保留全部适用事件，N/A单列；均值在搜索种子内先平均。主表按400/300/300实际测试构成汇总；分层和分扰动表单列。95%区间采用分层配对bootstrap，10000次、种子20261020；D1重采样基实例，轨道层先卫星组再基实例，另列只重采基实例的对照区间。测试仅两轨道组，组总体泛化能力有限。计时子集40/30/30事前抽取，20重复仅用于抖动，分布分散与同事件抖动分开。','', '操作比较共享输入、物理与冻结约束、50ms和B_max=5，但PALR自限局部邻域与累计预算、全局方法可改全部后缀，质量差异不能单归因控制器。择优固定(w5/B1)、固定默认(w5/B2)、冻结保守规则及PUCT温度0.5均未用测试重新选择。','', 'CP-SAT包含建模与求解成本；无解/UNKNOWN和建模超时均保留，不能据此宣称物理不可行。CP-SAT仅已返回并完整验证解才计严格可行；求解器状态不替代50ms在线验收。Python合作式截止及Docker/宿主机调度不提供硬实时保证。','', '公开轨道为既有快照假设派生接触，需求与日历为合成；同源星座不能当作独立实测通信来源。测试卫星组与训练/验证隔离，置信区间按基实例簇。','', '重建入口：python scripts/finalize_p4.py；原始main/timing分片保留完整计划与编辑轨迹，data保留全部输入及参考，test_freeze封存代码与参数。per_event_results.csv含每事件/方法/种子行，main_table.csv及timing_table.csv可由原始证据重建。','', '本阶段完成后停止；后续阶段等待用户指定。']
    (OUT/'P4_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='acceptance_manifest.json']
    save(OUT/'acceptance_manifest.json',dict(files={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in files},stage='P4'))
    print('P4 rebuilt and independently verified',flush=True)
if __name__=='__main__':main()
