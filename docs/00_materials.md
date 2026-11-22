# 材料目录与来源

首批归档来自 ICAPS 材料目录，共 7 份原件。`archive/manifest.csv` 记录相对路径、大小、SHA-256、材料角色及文本索引路径。

| ID | 原文件及仓库位置 | 用途与使用顺序 |
| --- | --- | --- |
| S01 | [任务完成进度汇总](../archive/requirements/ICAPS卫星修复完成进度汇总.docx) | 总任务、组会要求、投稿路线；日期需按官方纠正 |
| S02 | [20261020 论文要素](../archive/requirements/论文要素20261020.docx) | 历史论文修改要求与八项要素框架 |
| S03 | [PALR 中文原稿](../archive/papers/PALR.pdf) | 历史方法、实验、中文表达依据 |
| S04 | [PALR 英文原稿](../archive/papers/PALR_E.pdf) | 方法定义、表格数值、限制条件；存在 ACM 模板残留 |
| S05 | [加入星间时间窗和自适应参数的要素文档](../archive/drafts/PALR论文要素文档_加入星间时间窗与自适应参数.docx) | 扩展设计参考；不能当作已实现或已验证结果 |
| S06 | [第二步中文草稿](../archive/drafts/第二步（1）.docx) | 已有主题改写全文；保留原样，按审计表修正后再用 |
| S07 | [论文要素空模板](../archive/templates/论文要素空模板.docx) | 后续新版本填写模板 |

文本索引位于 [source_text](source_text/)，文件名以材料 ID 开头。Word 索引按段落展开（含表格中的段落），PDF 索引以原文件的物理页码标记。索引可能遗漏图片文字或复杂数学结构，不能替代原件。

## 版本使用规则

历史研究叙述以 S01–S06 的来源为依据。本轮《新要素文档》修订以已验证的 ISL 实现和实验为依据。对应口径见 [要素追踪](01_requirements.md)、[方法契约](04_method_contract.md)、[数据与基线](05_data_and_baselines.md) 和 [论文提纲](../paper/outline.md)，实验数字见 [P6 最终结果](../experiment_runs/reports/p6/P6-20261118/FINAL_RESULTS.md) 与对应专项。

## 历史原稿与投稿材料缺失

- 原 PALR、最小修复、贪心全局重优化、PUCT 与学习变体的源码及确切版本。
- 原实例生成器、50 个实例的具体种子、参考计划和扰动记录。
- 硬件、依赖环境、计时边界、每实例原始结果、置信区间生成代码。
- 学习方法的训练数据、权重、训练/验证/测试拆分和训练预算。
- 实测星间通信接触窗口。当前公开轨道来源和派生窗口规则见 [P1 生成契约](../experiment_runs/protocol/P1_GENERATION_CONTRACT.md)。
- LaTeX、BibTeX、可编辑图表与正式审稿记录。

后续收到材料时先登记来源和哈希，再接入对应目录。不要从 PDF 表格反向生成“逐实例原始数据”。
