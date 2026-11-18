"""P5 denominator/source/history/file acceptance; no new performance runs."""
import argparse,gzip,subprocess
from collections import Counter
from p5_common import *

PHASES=['ablations','calibration','mechanisms','simulations','upgrades','single_factor','windows','anomalies','references','transfer','continuous']
NAV=['experiment_runs/README.md','experiment_runs/STAGES.md','experiment_runs/status.json']

def history():
    old=load(OUT/'historical_bytes.json');changes=[];missing=[]
    for name,h in old.items():
        p=ROOT.parent/name
        if not p.exists():missing.append(name)
        elif sha(p)!=h:changes.append(name)
    unexpected=[n for n in changes if n not in NAV]
    r=dict(passed=not missing and not unexpected,tracked_historical_files=len(old),missing=missing,changed=changes,
        allowed_navigation_changes=NAV,unexpected_changes=unexpected,all_historical_scientific_evidence_unchanged=not missing and not unexpected)
    save(OUT/'historical_integrity.json',r);assert r['passed'],r
    return r

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--history-only',action='store_true');args=parser.parse_args()
    print('Checking all historical scientific evidence bytes',flush=True)
    hist=history()
    print('Historical integrity passed: '+str(hist['tracked_historical_files'])+' files',flush=True)
    if args.history_only:print(json.dumps(hist));return
    import pandas as pd
    sub=load(OUT/'subsets.json');summary=load(OUT/'summary_receipt.json');assert load(OUT/'input_independent_audit.json')['passed']
    assert load(OUT/'acceptance_details.json')['passed']
    assert load(OUT/'pipeline/COMPLETE.json')['complete']
    expected=dict(ablations=169200,calibration=720,mechanisms=14400,simulations=18000,upgrades=25200,single_factor=99840,windows=43200,anomalies=400,transfer=1440,continuous=4000)
    expected['references']=load(OUT/'references/COMPLETE.json')['successful_references']*48
    audit_counts={};raw_hashes={}
    for phase in PHASES:
        print('Checking P5 phase '+phase,flush=True)
        complete=load(OUT/phase/'COMPLETE.json');assert complete['calls']==expected[phase]
        freeze=OUT/phase/'source_freeze.json';frozen=load(freeze);assert sha(freeze)==complete['freeze']
        for name,h in frozen['sources'].items():assert sha(ROOT/name)==h,('frozen source changed',phase,name)
        jobs=frozen['extra']['specs'];expected_specs={(canonical_job(j),int(j.get('seed',11))) for j in jobs}
        for session in (OUT/phase/'sessions').glob('*.json'):
            warmup=load(session);assert warmup['affinity']==[0]
            assert len(warmup['warmups'])==20*len(jobs)
        if phase in ('single_factor','windows','anomalies'):
            expected_ids={r['key'] for r in load(OUT/'inputs'/phase/'manifest.json')['rows']}
        elif phase=='references':
            expected_ids={r['base_id'] for r in load(OUT/'references/initial_reference_summary.json')['results'] if r['status'] in ('OPTIMAL','FEASIBLE')}
        else:
            key={'ablations':'ablation_300','calibration':'validation_threshold_60','transfer':'cross_constellation_test','continuous':'continuous_100'}.get(phase,'special_100')
            expected_ids=set(sub[key])
        raw=[];c=Counter()
        for path in sorted((OUT/phase).glob('*.json.gz')):
            ident=path.name.removesuffix('.json.gz');receipt=load(path.with_suffix('.receipt.json'));assert sha(path)==receipt['sha256']
            verification=load(OUT/'audit'/phase/(ident+'.json'));assert verification['raw_sha256']==receipt['sha256'] and verification['freeze']==sha(freeze)
            assert sha(OUT/'audit'/phase/(ident+'.csv.gz'))==verification['flat_sha256'];c.update(verification['counts']);raw.append(ident)
            raw_hashes[path.relative_to(ROOT).as_posix()]=receipt['sha256']
        assert set(raw)==expected_ids,(phase,'raw IDs differ from predeclared expected set')
        assert c['calls']==expected[phase]
        df=pd.read_csv(OUT/'tables'/(phase+'_per_call.csv.gz'),keep_default_na=False)
        assert len(df)==expected[phase]
        assert set(zip(df.config,df.seed))==expected_specs
        for (_,scenario),group in df.groupby(['base_id','scenario']):
            keys=list(zip(group.config,group.seed));assert len(keys)==len(expected_specs) and set(keys)==expected_specs,(phase,scenario)
        audit_counts[phase]=dict(c)
    assert len(sub['ablation_300'])==300 and Counter(sub['layers'][i] for i in sub['ablation_300'])==dict(D1=100,**{'D2-S':100,'D2-O':100})
    assert len(sub['special_100'])==100 and len(sub['frozen_anomaly_50'])==50 and len(sub['cross_constellation_test'])==30
    assert len(sub['validation_threshold_60'])==60 and not load(OUT/'upgrade_threshold.json')['test_used']
    assert summary['total_formal_calls']==sum(expected.values())
    assert load(OUT/'ipc/applicability_audit.json')['applicability']['performance_events']=='not_run'
    sources=list((ROOT/'scripts').glob('*stage5*.py'))+[ROOT/'tests/test_p5_contract.py']
    save(OUT/'analysis_sources.json',dict(files={p.relative_to(ROOT).as_posix():sha(p) for p in sources},method_sources='per-phase source_freeze.json; original scientific sources unchanged'))
    result=dict(passed=True,stage='P5',P6_started=False,run_id='P5-20261118',formal_calls=sum(expected.values()),per_phase=audit_counts,
        predeclared_subsets_verified=True,independent_input_audit_passed=True,all_validated_outputs_replayed_by_original_checker=True,
        all_full_deadline_and_utility_scores_recomputed=True,complete_seed_sets_and_no_duplicate_event_calls=True,
        both_upgrade_phases_and_warm_cumulative_handoff_independently_checked=True,
        local_candidate_eligibility_and_original_A9_per_base_grid_checked=True,
        initial_CP_native_models_responses_and_feasible_plans_checked=True,continuous_state_and_delivered_utility_recomputed=True,
        historical_scientific_evidence_unchanged=hist['passed'],A1_A5_minimum_completed=True,
        completed_ablations=['A1','A2','A3','A4','A5-rule-only','A7','A8','A9-per-base-offline-grid-and-event-envelope','A10-rule'],
        not_applicable={'ET':'user-approved rule main line','A6':'depends on ET,not retrained','IPC_performance':'no full temporal planner/validator adapter,user-approved applicability audit only'},
        limitations=['frozen anomalies cover40D1+10Starlink,noOneWeb','reference sensitivity compares four light methods','exploratory CIs conditional on fixed orbit groups','Python cooperative timing,not hard real time','A9event-wise offline envelope is optimistic and not deployable','Rate changes base tasks;urgent rate follows original event generator;distance may change urgent endpoints when events are regenerated'],
        raw_shards=raw_hashes)
    save(OUT/'final_acceptance.json',result)
    # Domain-specific evidence gate: these checks assess the delivery contract,
    # not whether the algorithm improved or a manuscript is ready for submission.
    gate=dict(checkpoint_id='P5-delivery-evidence',status='PASS',score=100,
        score_scope='Percentage of required delivery checks passed; not scientific merit or performance superiority',
        failures=[],warnings=result['limitations'],stage='P5',P6_started=False,
        evidence=['final_acceptance.json','acceptance_details.json','input_independent_audit.json',
                  'historical_integrity.json','summary_receipt.json','preflight_tests.xml'],
        user_approved_not_applicable=result['not_applicable'])
    save(OUT/'paper_output/qa/evidence_gate_report.json',gate)
    (OUT/'paper_output/qa/evidence_gate_report.md').write_text(
        '# P5交付证据验收\n\n状态：PASS。100分仅表示本阶段所列交付门禁全部通过，不是算法优越性或论文质量评分。\n\n'
        '原始计划/轨迹与完整截止计分、分母及种子、同域资格、两阶段升级传递、逐基实例A9、CP原生证书、连续状态推进、历史字节保全已核验。'
        '证据见../../final_acceptance.json与../../acceptance_details.json。\n\n'
        '限制：ET/A6不适用；IPC性能未执行；冻结异常未覆盖OneWeb；区间仅为固定轨道组条件下P5探索性分析；Python合作式截止不提供硬实时保证。'
        '本验收不表示规则控制获益成立，不构成P6论文验收。\n',encoding='utf-8')
    tasks=[dict(id=k,status='verified',result_summary='Required call counts, source/input hashes and original-checker replay passed',
                evidence=f'../{k}/COMPLETE.json',metrics=f'../tables/{k}_summary.csv') for k in PHASES]
    save(OUT/'paper_output/tasks.json',dict(stage='P5',scope='Experiment evidence only; no manuscript generation authorized',tasks=tasks,
        not_applicable=result['not_applicable'],model_route='Frozen discrete ISL and P5 execution protocol',
        validation_plan='Full original-checker replay and stage-specific independent acceptance',
        conclusion='Applicable P5 experiments completed; performance claims bounded by P5_REPORT.md'))
    micro=OUT/'paper_output/micro_units';micro.mkdir(exist_ok=True)
    (micro/'.gitkeep').touch()
    (OUT/'memoryskill.md').write_text(
        '# Active memory\n\n## 长期准则\n\n一次只执行用户指定阶段；重要决策确认后推进；完成阶段报告并直接提交推送。不得自动启动P6。\n\n'
        '## 短期工作台\n\nP5证据门禁PASS；各正式批次分母、冻结源码、完整计时、独立重放通过，任务清单见paper_output/tasks.json。'
        '规则主线ET/A6不适用，IPC仅适用性审计。实验完成不等于规则优势或硬实时目标成立。'
        '完整结果见P5_REPORT.md，审计见final_acceptance.json。Git实际交付以推送后核验回执为准。P6未启动。\n',encoding='utf-8')
    print('Freezing complete delivery manifest',flush=True)
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='acceptance_manifest.json']
    assert not any(p.name.endswith('.tmp') for p in files),'Unfinished temp file remains'
    large=[str(p) for p in files if p.stat().st_size>=100*1024*1024];assert not large,large
    save(OUT/'acceptance_manifest.json',dict(stage='P5',run_id='P5-20261118',files={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in files}))
    print(json.dumps(dict(passed=True,formal_calls=result['formal_calls'],files=len(files),bytes=sum(p.stat().st_size for p in files),A6='N/A',IPC_performance='not_run',P6_started=False)),flush=True)

def canonical_job(j):
    from isl.models import canonical_json
    return canonical_json({k:v for k,v in j.items() if k not in ('seed','spec_id')})

if __name__=='__main__':main()
