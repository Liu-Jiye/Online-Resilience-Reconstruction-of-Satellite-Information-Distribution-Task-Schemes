"""Update current navigation only after P5 evidence acceptance; preserve old reports."""
from p5_common import *


def main():
    a=load(OUT/'final_acceptance.json');assert a['passed'] and not a['P6_started']
    state=load(ROOT/'status.json');state.update(workspace_status='P5_complete',next_stage='P6',next_stage_authorized=False,
        results_scope='P0-P5 and independently numbered supplements; P3-R validation includes default and N500-h0.8; P4 tests default load only; P5 adds ablations, load/window/reference/transfer/continuous sensitivity under its approved scope.')
    state['stages']['P5']=dict(status='complete',run_ids=['P5-20261118'],report='reports/p5/P5-20261118/P5_REPORT.md',
        formal_calls=a['formal_calls'],ablation_base_instances=300,special_base_instances=100,frozen_anomaly_cases=50,
        CP_reference_attempts=100,continuous_trajectories=100,ET_run=False,A6='not_applicable_user_approved',
        IPC_performance='not_run_user_approved_applicability_audit',independent_acceptance_passed=True,
        acceptance='reports/p5/P5-20261118/final_acceptance.json',performance_superiority_established=False)
    save(ROOT/'status.json',state)
    p=ROOT/'README.md';s=p.read_text(encoding='utf-8-sig')
    s=s.replace('P3-R 和 P4 已完成；P5/P6 未启动。','P3-R、P4 和 P5 已完成；P6 未启动。')
    line='| P5 | 300分层消融、100专项、50冻结异常、100 CP参考尝试、100连续轨迹；规则主线，ET/A6不适用，IPC仅适用性审计 | [阶段报告](reports/p5/P5-20261118/P5_REPORT.md)、[验收](reports/p5/P5-20261118/final_acceptance.json)、[原始证据与复算](reports/p5/P5-20261118/REPRODUCE.md) |\n'
    assert '| P5 |' not in s
    s=s.replace('| 历史对话整理 |',line+'| 历史对话整理 |')
    s=s.replace('本次整理不重跑实验、不改参数、不启动后续阶段。','历史整理不重跑旧实验；随后按用户授权独立完成P5，原有方法及旧结果保留。P5完成后停止，P6尚未获授权。')
    s+='\n## P5交付与解释边界\n\nP5完整调用、失败和种子行均已封存并独立复算；同邻域机制与历史全后缀操作比较分表。完成适用实验不等于规则优越性或硬实时成立，结果与限制以P5报告为准。[P0–P4评估](reports/p5/P5-20261118/prior_stage_review/P0_P4_REVIEW.md)及[两日期交付完整性复核](reports/p5/P5-20261118/prior_stage_review/historical_delivery_completeness.json)同步保存。\n'
    p.write_text(s,encoding='utf-8')
    p=ROOT/'STAGES.md';s=p.read_text(encoding='utf-8-sig')
    s=s.replace('P3-R 和 P4 已完成，P5/P6 未启动','P3-R、P4 和 P5 已完成，P6 未启动')
    s+='\nP5实际完成范围与验收见[阶段报告](reports/p5/P5-20261118/P5_REPORT.md)和[最终验收](reports/p5/P5-20261118/final_acceptance.json)。A5/A10采用用户批准的规则主线；ET/A6不适用，IPC性能未执行、适用性审计单列。A9保留原方案逐基实例离线网格，另列逐事件包络。P6未启动，后续阶段由用户指定。\n'
    p.write_text(s,encoding='utf-8')
    print('P5 navigation complete; P6 not started')


if __name__=='__main__':main()
