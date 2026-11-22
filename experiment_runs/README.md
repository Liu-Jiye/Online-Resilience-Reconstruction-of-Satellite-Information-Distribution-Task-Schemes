# 分阶段实验执行工作区

本目录专门保存本项目实验的实现、配置、数据登记、日志和结果。**截至 2026-11-18，P0–P6及P3-R已完成，实验按用户指定范围结束。** 实际验收状态以 [状态文件](status.json) 和对应阶段报告为准。仓库根 README 保留原资料整理时的文字，当前实验进度以本页为准。

## 当前交付入口

[短预算紧急任务优先修复](reports/palr_short_budget/REPORT.md)提供 10 ms 和 20 ms 的可选入口、配对回放与复现命令。

当前论文和汇总使用 [P5 A5 复跑结果表](reports/palr_rule_ablations/REPORT.md#p5-a5-复跑结果)。P5、P6 封存报告中的首次 A5 表、图和配对统计对应历史验收批次。

| 阶段/材料 | 规模与状态 | 入口 |
|---|---|---|
| P5 A5 参数规则消融 | 复跑结果覆盖 300 个基实例、3,600 个共同事件，含共享算子优化的固定对照 | [现行结果表](reports/palr_rule_ablations/REPORT.md#p5-a5-复跑结果)、[完整统计](reports/palr_rule_ablations/acceptance.json) |
| PALR 自适应算子专项复跑 | P4 默认负载 1,000 基实例、12,000 事件、四方法 48,000 次调用，提速验收通过 | [专项报告](reports/palr_adaptive_rerun/REPORT.md)、[验收统计](reports/palr_adaptive_rerun/acceptance.json)、[运行协议与复现](protocol/PALR_ADAPTIVE_RERUN.md) |
| P6最终统计 | 10000次配对簇重采，轨道先组再实例；573200主/专项调用评分复核，9图 | [阶段报告](reports/p6/P6-20261118/P6_REPORT.md)、[最终结果](reports/p6/P6-20261118/FINAL_RESULTS.md)、[验收](reports/p6/P6-20261118/final_acceptance.json)、[复现指南](reports/p6/P6-20261118/REPRODUCE.md) |
| P3 | 4000 训练+1000 验证，默认/中竞争配对，992000 记录 | [报告](reports/P3_REPORT.md)、[冻结参数](reports/p3/P3-20261110/frozen_parameters.json) |
| P3-R | 168000 次修订验证，精简 ET 无预定净收益，两层保留规则；中竞争工程目标未全部达到 | [报告](reports/p3r/P3R-20261112/P3R_REPORT.md)、[完整证据](reports/p3r/P3R-20261112/) |
| P4 | 仅默认负载、八项基线，1000 测试基实例×12=12000 事件；192000 主调用+384000 计时调用 | [报告](reports/p4/P4-20261117/P4_REPORT.md)、[主表](reports/p4/P4-20261117/main_table.csv)、[逐事件结果](reports/p4/P4-20261117/per_event_results.csv)、[复现说明](reports/p4/P4-20261117/REPRODUCE.md) |
| P5 | 300分层消融、100专项、50冻结异常、100 CP参考尝试、100连续轨迹；规则主线，ET/A6不适用，IPC仅适用性审计 | [阶段报告](reports/p5/P5-20261118/P5_REPORT.md)、[验收](reports/p5/P5-20261118/final_acceptance.json)、[原始证据与复算](reports/p5/P5-20261118/REPRODUCE.md) |
| 历史对话整理 | 批准范围、设计变更、证据边界及交付缺口 | [整理说明](deliveries/HISTORY_RECONCILIATION.md) |
| 全部历史交付 | 两日期卫星项目工作区 outputs 的全部 103 个文件，原始字节归档 | [归档与 ZIP 还原](deliveries/README.md)、[来源及哈希清单](deliveries/catalog.json) |

两个超过 GitHub 单文件限制的原始 ZIP 按 32 MiB 分卷，不重新压缩；展开后的原始证据也已保存在 reports 中。标准库只读核验及可选还原命令（从仓库根目录执行）：

```bash
python experiment_runs/scripts/verify_delivery.py
python experiment_runs/scripts/verify_delivery.py --restore-dir ./restored
python experiment_runs/scripts/verify_p3.py
python experiment_runs/scripts/verify_p3r.py
python experiment_runs/scripts/verify_archived_stages.py
```

贡献定位仍为“快速完成轻量局部修复，并明确何时需要更强搜索”。P4 默认层固定择优成功率 70.9583%、规则 70.6250%，配对区间跨零，不能声称规则优于固定，也不依据测试重新选参。P4 使用完整方法调用 50ms，P3-R 保留内核响应计时，不能混用。主表紧急服务率包含迟到，预算内服务率及有效输出条件干扰见 [conditional_quality.csv](reports/p4/P4-20261117/conditional_quality.csv)。所有方法 p99>50ms，不提供硬实时保证。

历史报告中的“未进入 P4”“尚未提交或推送”保留封存时含义，不据此判断当前状态。历史整理不重跑旧实验；随后按用户授权完成P5和最终P6，原有方法及旧结果保留。用户取消未交付中竞争P4-M/P5-M，其容器已停止移除；本地删除被自动审批拒绝，未跟踪残留排除统计与Git交付。P5原已交付N500/N1000单因素保留。P6后停止，不自动开展新实验。

## 工作边界与依据

- 本轮及后续实验新增和修改的文件全部限定在 `experiment_runs/` 内；仓库其他已有文件保持不变。
- 执行依据为 [完整实验方案](../experiments/complete_experimental_plan.md) 和 [机器可读设计](../experiments/configs/experimental_design_v1.json)。初始化时保存了逐字节协议快照及 SHA-256，见 [来源清单](protocol/source_manifest.json)。
- [阶段计划](STAGES.md) 记录依赖与验收；[阅读与实现决策](REVIEW_NOTES.md) 记录已识别的语义冲突和证据边界；[状态文件](status.json) 记录真实进度。
- 当前仓库缺少原算法源码、原生成器、原种子、权重及逐实例日志。后续自行实现必须标记为重新实现；历史观测模型标记 `HIST-reimplementation`，新增通信模型标记 `ISL`。

## 目录用途

| 位置 | 内容 |
| --- | --- |
| `protocol/` | 原方案和配置快照、来源版本、哈希 |
| `src/` | 后续模型、窗口、算法、控制、指标和执行器代码 |
| `tests/` | 独立校验、边界检查和精确参照对齐 |
| `configs/` | 阶段运行配置、冻结后的参数及协议修订 |
| `scripts/` | 后续生成、运行、验证、统计、作图入口 |
| `data/` | 来源登记、数据卡和划分清单；原始/派生大数据本地存放 |
| `runs/` | 每批实验的配置、环境、逐事件计划、校验和原始结果 |
| `reports/` | 阶段报告、汇总表、失败审计、图表 |
| `environment/` | 实际安装验证后的依赖锁、硬件和环境记录 |

目录中的 `.gitkeep` 仅用于 Git 跟踪空目录。P0 的可运行代码位于 `src/isl/`，入口位于 `scripts/`，正确性检查位于 `tests/`。

## 执行与结果规则

按 P0 → P1 → P2 → P3 → P4 → P5 → P6 逐阶段推进；每次仅执行用户指定阶段并形成阶段报告，完成后停下，后续阶段由用户决定。尚未实现的 CLI 不能作为已执行命令展示。

P0 语义、HIST 差异和复跑说明见 [实现契约](protocol/P0_IMPLEMENTATION_CONTRACT.md)；原代码缺失登记见 [原始工件清单](protocol/original_artifacts.json)。在独立环境中运行 `experiment_runs/scripts/run_p0.py` 可执行 P0 正确性验收，另有 `run_case.py` 单例入口。原仓库 `python scripts/validate_repository.py` 仍仅检查资料完整性。

P0 已完成：115 项检查通过，12 事件×3 方法联调并独立复核，见 [P0 阶段报告](reports/P0_REPORT.md)。P1 已完成：150/150 有效试点、125 项检查通过、320 对象/星座及全局划分隔离通过，见 [P1 阶段报告](reports/P1_REPORT.md)、[冻结生成契约](protocol/P1_GENERATION_CONTRACT.md) 和 [正式证据批次](reports/p1/P1-20261105T110427Z/)。原 P1 未触发负载修订，后续独立负载试点见 LOAD 报告；原始 GP 不上传，公开派生实例包可独立复核。P2 已完成：366 次尝试生成 300 个有效基实例，200 个事件全部取得离散局部域最优；另 64 个紧急服务子问题证明不可行，264 个模型全部重放通过，140 项检查通过。见 [P2 报告](reports/P2_REPORT.md)、[精确参照契约](protocol/P2_EXACT_CONTRACT.md) 及 [证据批次](reports/p2/P2-20261105T114327Z/)。这是 P2 完成时的历史统计，后续完成状态见本页顶部与总状态。

实际运行时，每批使用独立 `runs/<run_id>/`，禁止覆盖旧结果；至少保存协议与代码版本、环境、数据哈希、划分/实例/事件 ID、参考计划、冻结项、种子、输出计划、独立校验、计时分项、参数轨迹及失败原因。超时、服务失败、未知可行性与证明不可行分开统计，失败事件不得从分母删除。

本目录的 `.gitignore` 将原始/派生数据、本地环境和大批运行原件排除出默认提交。小型配置、哈希清单、汇总与报告可入库；完整大数据发布固定版本及校验清单，报告必须指向对应原始证据，不能仅发布均值。第三方数据按来源条款处理。

## P5交付与解释边界

P5完整调用、失败和种子行均已封存并独立复算；同邻域机制与历史全后缀操作比较分表。完成适用实验不等于规则优越性或硬实时成立，结果与限制以P5报告为准。[P0–P4评估](reports/p5/P5-20261118/prior_stage_review/P0_P4_REVIEW.md)及[两日期交付完整性复核](reports/p5/P5-20261118/prior_stage_review/historical_delivery_completeness.json)同步保存。

P6的[本地七份导出材料原字节归档](reports/p6/delivery_exports/P6-20261118/)包含中文阶段报告、结果摘要、复现指南、最终验收、报告/表格/九图ZIP、Git核验回执及导出哈希清单。ZIP是便于阅读的材料包，完整10000重复数组、整数重采频数及逐调用复核在[P6科学封存目录](reports/p6/P6-20261118/)中直接交付，不重复塞入阅读ZIP。Git回执核验科学提交，随后以独立交付提交归档该回执及同字节导出文件。
