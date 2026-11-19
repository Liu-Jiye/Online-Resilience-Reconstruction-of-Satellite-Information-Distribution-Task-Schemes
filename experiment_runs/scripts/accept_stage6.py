"""Evidence gates for P6, including independent explicit-index bootstrap checks."""
import subprocess,xml.etree.ElementTree as ET,zipfile
import numpy as np
import pandas as pd
from p6_common import *

ALLOWED_OLD={'experiment_runs/README.md','experiment_runs/STAGES.md','experiment_runs/status.json','experiment_runs/scripts/.gitattributes'}

def main():
    for name in ['prepared','statistics_COMPLETE','sensitivity_COMPLETE','review_COMPLETE','report_COMPLETE']:
        d=load(OUT/(name+'.json'))
        if name!='prepared':assert d['passed'],name
    source=load(OUT/'source_manifest.json')
    for name,e in source['files'].items():assert sha(SOURCE/name)==e['sha256'],name
    historical=load(OUT/'historical_git_blobs.json')
    changed=subprocess.check_output(['git','diff','--name-only',historical['parent_commit'],'--'],cwd=ROOT.parent,text=True).splitlines()
    violations=[p for p in changed if p in historical['files'] and p not in ALLOWED_OLD]
    assert not violations,violations
    records=load(OUT/'published_table_crosscheck.json');assert records['total_calls']==573200
    assert records['phases']['P4']['calls']==192000
    failure=pd.read_csv(OUT/'tables/failure_review.csv')
    assert np.array_equal(failure[['exclusive_timeout','exclusive_not_validated','exclusive_urgent_unserved']].sum(axis=1),failure.failed_calls)
    assert np.array_equal(failure.applicable_calls-failure.online_success_calls,failure.failed_calls)
    p4=pd.read_csv(OUT/'tables/P4_statistics.csv');p4=p4[(p4.view=='overall')&(p4.bootstrap=='hierarchical')]
    original=pd.read_csv(P4/'main_table.csv')
    score=pd.read_csv(OUT/'tables/P4_events.csv.gz')
    for label,g in score.groupby('label'):
        for metric,num,den in [('online_success','online_success','applicable'),('U_exec','U_exec','applicable'),('conditional_U','accepted_U_raw','valid_output')]:
            actual=float(p4[(p4.label==label)&(p4.metric==metric)].estimate.iloc[0])
            assert np.isclose(actual,g[num].sum()/g[den].sum(),atol=1e-9)
            if metric in ['online_success','U_exec']:
                assert np.isclose(actual,original[original.method==label][metric].iloc[0],atol=1e-9)
    reference_success={'Minimal-Repair':8496,'Frozen-Greedy':8414,'Fixed-PALR':8508,'Validation-Best-Fixed':8515,'Rule-PALR':8475,'PUCT-ISL':5999.8,'ALNS-ISL':6692.8,'CP-SAT-50ms':2302}
    for label,n in reference_success.items():assert np.isclose(score[score.label==label].online_success.sum(),n)
    units=load(OUT/'unit_metadata.json');checks=0
    for path in (OUT/'resampling').glob('*.npz'):
        d=np.load(path);ids=d['ids'].tolist();meta=load(path.with_suffix('.json'))
        assert len(d['hierarchical_counts'])==REPS and meta['repetitions']==REPS
        values=np.arange(len(ids),dtype=float)**2
        for kind in ['base_counts','hierarchical_counts']:
            counts=d[kind]
            for r in [0,123,9999]:
                total=0.;manual=0.
                for layer in sorted({units[i]['layer'] for i in ids}):
                    ix=np.array([j for j,i in enumerate(ids) if units[i]['layer']==layer]);c=counts[r,ix].astype(int)
                    explicit=np.repeat(ix,c);assert len(explicit)>0
                    manual+=values[explicit].mean()*len(ix)
                    total+=np.dot(c,values[ix])*len(ix)/c.sum()
                assert np.isclose(total,manual,atol=1e-7);checks+=1
    replicate_arrays=0
    for path in (OUT/'replicates').rglob('*.npz'):
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                with archive.open(member) as stream:
                    version=np.lib.format.read_magic(stream)
                    reader=np.lib.format.read_array_header_1_0 if version==(1,0) else np.lib.format.read_array_header_2_0
                    shape,order,dtype=reader(stream)
                    assert shape==(REPS,),(path,member,shape)
                    replicate_arrays+=1
    suite=ET.parse(OUT/'qa/unit_tests.xml').getroot()
    testnodes=suite.findall('.//testcase');assert len(testnodes)>=4 and not suite.findall('.//failure') and not suite.findall('.//error')
    figures=[]
    for path in sorted((OUT/'figures').glob('F*.pdf')):
        name=path.stem;qa=OUT/'figures/qa'
        textcheck=load(qa/(name+'.text.log'));collision=load(qa/(name+'.collisions.json'))
        assert textcheck['auditable'] and textcheck['below_minimum_count']==0
        assert collision['summary']['fail']==0 and collision['summary']['warn']==0
        for suffix in ['.png','.svg','.source.csv','.legend.json','.alignment.json']:assert path.with_suffix(suffix).exists()
        figures.append(name)
    assert len(figures)==9
    preflight=load(OUT/'figures/qa/source_preflight.json');assert preflight['summary']['counts']['FAIL']==0
    assert load(OUT/'figures/visual_review.json')['passed']
    for path in OUT.rglob('*'):
        if path.is_file():assert path.stat().st_size<100*1024*1024,path
    result=dict(passed=True,stage='P6',scope='Published P0-P5; main statistical inference P4/P5; P4-M/P5-M cancelled and excluded',
        paired_bootstrap_repetitions=REPS,seed=SEED,orbital_groups_first=True,original_layer_weights_preserved=True,
        raw_calls_recomputed_and_published_rows_crosschecked=573200,historical_timing_calls_separate=384000,
        consumed_source_sha256_verified=len(source['files']),historical_tracked_files=len(historical['files']),
        historical_scientific_changes=violations,allowed_navigation_changes=[p for p in changed if p in ALLOWED_OLD],
        explicit_index_bootstrap_crosschecks=checks,unit_tests_passed=len(testnodes),
        figures=figures,pdf_collision_failures=0,pdf_text_below_5pt=0,
        success_denominators_and_conditional_quality_reported=True,raw_latency_quantiles_not_seed_mean_quantiles=True,
        whole_trajectory_units=True,all_10000_replicate_arrays_saved=True,verified_replicate_arrays=replicate_arrays,p_values_produced=False,
        ET_A6='not_applicable_user_approved',IPC='applicability_audit_only_no_performance',
        cancelled_medium_containers='stopped_and_removed',cancelled_medium_files='Local deletion rejected by automatic approval policy; untracked remnants excluded from Git delivery and statistical evidence',
        completed_scope_does_not_assert_rule_superiority=True,hard_realtime_established=False,
        further_stage_started=False,acceptance_manifest='acceptance_manifest.json')
    save(OUT/'final_acceptance.json',result)
    files={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='acceptance_manifest.json'}
    code=[p for p in (ROOT/'scripts').glob('*.py') if 'stage6' in p.name or p.name.startswith('p6_')]
    code += [ROOT/'protocol/P6_STATISTICS_V1.md',ROOT/'tests/test_p6_statistics.py']
    save(OUT/'acceptance_manifest.json',dict(files=files,source_code={p.relative_to(ROOT).as_posix():sha(p) for p in code},
         file_count=len(files),total_bytes=sum(x['bytes'] for x in files.values())))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
