"""Starlink-only selection using sealed P3 validation cells; OneWeb test untouched until selection."""
from p5_runner import *

def main():
    selections={}
    for mode in ('grid','rules'):
        summary=load(P3/(mode+'_summary.json'));rank=[]
        for config_row in summary['configurations']:
            if config_row['load']!='default':continue
            cells=[c for c in config_row['cells'] if c['layer']=='D2-S'];assert len(cells)==12
            success=float(np.mean([c['online_success']/c['applicable'] for c in cells]))
            utility=float(np.mean([c['normalized_U_exec_sum']/c['applicable'] for c in cells]))
            rank.append(dict(setting=config_row['setting'],success=success,normalized_U_exec=utility))
        selections[mode]=min(rank,key=lambda x:(-x['success'],-x['normalized_U_exec'],str(x['setting'])))
    config_source=load(ROOT/'configs/p3_v1.json')
    rules={r['name']:{k:v for k,v in r.items() if k!='name'} for r in config_source['rule_candidates']}
    selected=selections['rules']['setting'];assert selected in rules
    selection=dict(selection_source='P3 default D2-S validation cells only',selections=selections,rule=rules[selected],
        test_used=False,OneWeb_validation_used=False,ET='not_applicable_user_confirmed',
        policy='12 Starlink scenario macro online success, then normalized execution utility, then deterministic setting string',
        source_sha256={mode:sha(P3/(mode+'_summary.json')) for mode in ('grid','rules')})
    sealed(OUT/'transfer_selection.json',selection)
    w,b=selections['grid']['setting'];jobs=[dict(name='Minimal-Repair'),dict(name='Fixed-PALR',w=5,B=2),dict(name='Validation-Best-Fixed',w=w,B=b),dict(name='Rule-PALR')]
    sub=load(OUT/'subsets.json');_,stats=config();rule=selection['rule'];freeze=frozen_phase('transfer',dict(specs=jobs,selection_sha256=sha(OUT/'transfer_selection.json')))
    session=warm(jobs,rule,stats,'transfer');n=0
    for ident in sub['cross_constellation_test']:
        n+=collect('transfer',ident,'D2-O',cases(base_data(ident)),jobs,rule,stats,freeze,session,dict(selection_sha256=sha(OUT/'transfer_selection.json'),direction='Starlink-selection_to_OneWeb-test'))
    save(OUT/'transfer/COMPLETE.json',dict(bases=len(sub['cross_constellation_test']),calls=n,freeze=freeze))

if __name__=='__main__':main()
