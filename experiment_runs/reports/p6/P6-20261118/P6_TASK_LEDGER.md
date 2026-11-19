# P6 任务与证据对照

| 用户验收项 | 可追溯证据 |
| --- | --- |
| 10000次配对簇bootstrap | p6_bootstrap.py、resampling/、replicates/、statistics_COMPLETE.json |
| 轨道先组再实例 | 每抽样计划JSON的orbit_groups和整数hierarchical_counts；测试不等组大小与固定层权重 |
| 分层效应和95%区间 | P4/P5各专项statistics/effects表，P4完整36单元，层级与仅实例区间分列 |
| 成功数和分母 | statistics表success_equivalent/applicable_equivalent/raw_calls/base_clusters；搜索五种子平均明确 |
| 有效输出条件质量与U_exec | 有效掩码在种子均值前应用；条件分子/分母重采；双方全部种子有效交集另列 |
| 延迟分位数与超时 | raw_call_latency.csv；P4_twenty_repeat_timing.csv单列历史抖动；不对种子均值取分位数 |
| 失败复核 | raw_audit/、published_table_crosscheck.json、failure_review.csv、solver_statuses.csv和同输入可行见证列表 |
| 连续事件 | trajectory_statistics/effects；100整轨迹、交付效用、恢复和窗错失 |
| CP参考与IPC | reference统计与配对条件敏感性；IPC保留原适用性审计，不伪造性能结果 |
| 图表脚本与审查 | plot_stage6.py，九图PNG/PDF/SVG和来源CSV、说明、PDF字号/碰撞审查 |
| 来源哈希与复现 | source_manifest、原始分片哈希、historical_git_blobs、acceptance_manifest、REPRODUCE.md |
| 阶段报告与停止 | P6_REPORT.md、FINAL_RESULTS.md、STAGE_MEMORY.md；P6为最后阶段，不自动继续 |
| 取消P4-M/P5-M | 容器已停止移除，未交付证据排除；本地删除被自动审批拒绝，残留不暂存 |

最终通过与计数以final_acceptance.json为准。阶段完成不等于规则优越、硬实时或未适用分支已运行。
