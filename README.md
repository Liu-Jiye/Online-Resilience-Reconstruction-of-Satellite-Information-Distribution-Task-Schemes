# 动态扰动环境下卫星信息分发任务方案的在线韧性重构

本仓库归档 PALR 原论文和论文要素材料，并提供单跳星间传输（ISL）的重实现、配置、实验数据说明及结果。当前实验进度见 [实验工作区](experiment_runs/README.md)，主实验与统计见 [P6 最终结果](experiment_runs/reports/p6/P6-20261118/FINAL_RESULTS.md)。历史观测调度结果按原论文引用，原算法、实例生成器、种子、训练权重及逐实例日志仍待恢复。

## 从这里开始

1. 通过 [实验工作区](experiment_runs/README.md) 查看代码、配置、阶段报告和逐事件结果。
2. 按 [材料目录](docs/00_materials.md) 查找历史来源与修订后的论文要素口径。
3. 用 [需求追踪矩阵](docs/01_requirements.md)、[方法接口与约束](docs/04_method_contract.md)、[数据与基线](docs/05_data_and_baselines.md) 和 [论文提纲](paper/outline.md) 对齐论文。
4. 查阅实验设计时使用 [初始完整方案](experiments/complete_experimental_plan.md) 和 [机器可读设计](experiments/configs/experimental_design_v1.json)。实际执行、范围及证据以 [阶段报告](experiment_runs/STAGES.md) 为准。
5. 论文中的 P5 A5 参数规则消融统一引用 [3,600 个事件的复跑结果表](experiment_runs/reports/palr_rule_ablations/REPORT.md#p5-a5-复跑结果)。

## 目录

```text
archive/
  papers/                 PALR 中文、英文原始 PDF
  requirements/           任务进度汇总、20261020 论文要素要求
  drafts/                 第二步中文草稿、加入扩展的论文要素文档
  templates/              论文要素空模板
docs/
  source_text/            Word 文本索引和 PDF 按页文本索引
  00_materials.md         材料入口与缺失项
  01_requirements.md      八项论文要素到产出和验收标准的映射
  02_audit.md             跨版本冲突与修正建议
  03_roadmap.md           按依赖排序的后续任务
  04_method_contract.md   算法实现必须满足的语义
  05_data_and_baselines.md 数据与基线核验入口
  06_submission.md        官方截止时间、格式与提交检查
paper/                    论文重写提纲、贡献与证据映射
data/                     数据字段、来源记录模板
experiments/              历史协议、扩展实验配置和结果记录模板
experiment_runs/          当前 ISL 实现、配置、阶段报告和结果
src/                      原资料整理阶段的源码接入说明
scripts/                  材料索引提取与仓库完整性校验
.github/                  后续任务和修改审查模板
```

## 快速检查

Python 3.10+；完整性校验只使用标准库：

```bash
python scripts/validate_repository.py
```

如需重新生成可检索文本（非实验复现）：

```bash
python -m pip install -r requirements-tools.txt
python scripts/extract_sources.py
```

原始归档文件见 [SHA-256 清单](archive/manifest.csv)。公式与表格以原 PDF/DOCX 为准。

## 当前完成情况

| 工作 | 状态 |
| --- | --- |
| 7 份原始文件分类、校验与文本索引 | 已整理 |
| 要素需求、修改顺序、模型与实验规范 | 已整理 |
| ICAPS 2027 官方日期与页数核验 | 已核验，见提交说明 |
| 原 PALR 源码、种子与逐实例结果恢复 | 待补 |
| 星间窗口、双端资源与状态驱动 w/B | 已实现和评估，见 P0–P6 |
| 公开轨道要素与接触窗派生 | Starlink、OneWeb 派生场景进入主测，IPC 完成适用性审计 |
| ICAPS 录用论文数据与消融调研、第三方论文源码核验 | 待补 |
| AAAI-27 论文源文件、审稿回复与视频 | 待开展 |

## 材料使用

本次没有替原始论文或第三方数据声明开源许可证。公开仓库中的可读取性不等同于取得再分发、商业使用或衍生使用授权。新增代码正式发布前由作者确定许可证；第三方资料保留其原有权利与许可要求。匿名投稿包应单独构建，避免直接使用含身份信息的公开仓库链接。
