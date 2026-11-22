# 论文要素需求追踪矩阵

本表沿用 S02 的要素框架。模型、方法、数据与实验各项对齐本轮《新要素文档》修订口径，依据当前 ISL 实现及 [实验工作区](../experiment_runs/README.md)。历史来源见 [材料目录](00_materials.md)。

| ID | 要素或要求 | 当前材料 | 后续产出 | 验收标准 |
| --- | --- | --- | --- | --- |
| R01 | 背景与场景 | S02、S05、S06 | 引言第一段、场景图 | 地面网络背景简短引出 LEO 信息分发；区分观测与传输模型 |
| R02 | 业务问题 | S02、S05 | 场景及需求段 | 解释承诺保持、紧急响应、窗口利用和协调成本 |
| R03 | 研究思路 | [当前方法契约](04_method_contract.md) | 方法总览 | 冻结前缀、原索引邻域、累计新接纳预算、硬约束和词典序构成完整流程 |
| R04 | 技术科学问题 | S02、[P0 实现契约](../experiment_runs/protocol/P0_IMPLEMENTATION_CONTRACT.md) | 建模及难点 | 形式化双端联合可行性、紧急服务与效用/干扰的裁决、w/B 选择 |
| R05 | 技术思路 | [ISL 修复源码](../experiment_runs/src/isl/repair.py)、[裁决源码](../experiment_runs/src/isl/metrics.py) | 算法框、性质说明 | 正文与代码一致，明确冻结冲突、邻域、预算、紧急优先和独立校验 |
| R06 | 创新点 | S04、[当前实验报告](../experiment_runs/README.md) | 贡献段与相关工作对照 | 说明历史机制、已实现的窗口扩展和已评估的参数控制 |
| R07 | 实验数据 | [数据与基线](05_data_and_baselines.md) | 论文数据与历史结果说明 | 区分历史观测协议、合成 ISL 和公开轨道派生层，明确规模及 IPC 审计边界 |
| R08 | 实验设计 | [执行与验收](../experiment_runs/STAGES.md)、[数据与基线](05_data_and_baselines.md) | 论文实验与复现说明 | 正式八基线、指标及失败分母、实际消融与配对统计可追溯，录用论文和第三方源码待核验项明确 |
| R09 | 星间接触时间窗 | [P0 实现契约](../experiment_runs/protocol/P0_IMPLEMENTATION_CONTRACT.md)、[P5 消融报告](../experiment_runs/reports/p5/P5-20261118/P5_REPORT.md) | 论文模型及正确性说明 | 单窗口覆盖含建链的整数占用，双端终端和忙日历通过独立校验 |
| R10 | 状态驱动的 w/B 选择 | [冻结参数](../experiment_runs/reports/p3/P3-20261110/frozen_parameters.json)、[规则消融](../experiment_runs/reports/palr_rule_ablations/REPORT.md) | 论文方法及实验说明 | 固定、仅 B、仅 w、联合规则及网格参照，在线控制开销计入总时延 |
| R11 | 多模型审稿与逐项回复 | S01 只有要求 | 审稿意见表、修改记录 | 每条意见有出处、处置、位置和证据；不能伪造已审稿记录 |
| R12 | 逐段表达修订 | S01、S06 | 中英文修订稿 | 一致使用计划修复术语，删除可行性上限等过强表述 |
| R13 | 格式、附录、视频、源码数据公开 | S01 | AAAI-27 稿、匿名补充包 | 长文正文 8 页；引用/许可清晰；匿名包可独立复现 |

论文各节承载位置见 [重写提纲](../paper/outline.md)。R09/R10 已有实现和实验，当前入口见 [实验工作区](../experiment_runs/README.md)。R07 的执行进度也见该入口。R11 尚无真实审稿记录。
