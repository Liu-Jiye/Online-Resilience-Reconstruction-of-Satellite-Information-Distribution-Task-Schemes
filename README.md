# 动态扰动环境下卫星信息分发任务方案的在线韧性重构

本仓库整理 PALR 原论文、ICAPS 修改要求和已有中文草稿，支撑后续模型扩展、源码恢复、实验复现与投稿。资料整理日期：2026-11-04。

**当前是研究资料与实施规范仓库，尚无原始算法源码、实例数据、训练权重和逐实例实验日志。原稿中的结果属于作者已报告结果，本次没有重新运行实验。星间接触窗口与自适应 w/B 尚待实现与验证。**

## 从这里开始

1. 阅读 [材料目录](docs/00_materials.md)，找到原稿和每份文件的用途。
2. 按 [需求追踪矩阵](docs/01_requirements.md) 对齐《论文要素20261020.docx》。
3. 先处理 [原稿问题与证据边界](docs/02_audit.md)，再开展论文修改。
4. 按 [后续任务清单](docs/03_roadmap.md) 恢复代码、补充约束与实验。
5. 实现时使用 [方法接口与约束](docs/04_method_contract.md)、[数据规范](data/README.md) 和 [实验协议](experiments/README.md)。
6. 开展实验时按 [完整实验方案](experiments/complete_experimental_plan.md) 执行，配套 [机器可读设计](experiments/configs/experimental_design_v1.json) 明确模型、数据规模、指标、基线、消融和验收。

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
src/                      后续代码接入说明
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

原文件保持字节不变，见 [SHA-256 清单](archive/manifest.csv)。文字索引不保留全部版式、图片和公式排版，核对公式与表格时以原 PDF/DOCX 为准。原始 D 盘文件未移动或修改。用户所称“ICAPS卫星修复任务汇总.docx”在目录中不存在；本仓库采用实际存在的“ICAPS卫星修复完成进度汇总.docx”，并记录了名称差异。

## 当前完成情况

| 工作 | 状态 |
| --- | --- |
| 7 份原始文件分类、校验与文本索引 | 已整理 |
| 要素需求、修改顺序、模型与实验规范 | 已整理 |
| ICAPS 2027 官方日期与页数核验 | 已核验，见提交说明 |
| 原 PALR 源码、种子与逐实例结果恢复 | 待补 |
| 星间窗口与自适应参数实现、实验 | 待开展 |
| 公开数据选定、下载及字段适配 | 待开展 |
| AAAI-27 论文源文件、审稿回复与视频 | 待开展 |

## 材料使用

本次没有替原始论文或第三方数据声明开源许可证。公开仓库中的可读取性不等同于取得再分发、商业使用或衍生使用授权。新增代码正式发布前由作者确定许可证；第三方资料保留其原有权利与许可要求。匿名投稿包应单独构建，避免直接使用含身份信息的公开仓库链接。
