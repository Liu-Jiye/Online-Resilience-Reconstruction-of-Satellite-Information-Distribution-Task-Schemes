# 历史交付材料归档（2026-11-18）

本目录逐文件保存两个历史工作区 `outputs/` 中的全部交付材料，原名与原始字节保留。空的同日其他 GitHub 工作区没有交付文件；同日 LM324 工作区与卫星项目无关，不纳入。阶段原始数据、完整计划与脚本位于 `experiment_runs/reports/`、`src/`、`scripts/`，本目录保存用户当时收到的交付版本，允许必要的重复。

- [历史要求、决策和证据边界整理](HISTORY_RECONCILIATION.md)
- [逐文件来源、大小和 SHA-256 清单](catalog.json)
- [2026-11-05 交付目录](2026-11-05/)：P0、P1、P2、紧急诊断与补充、P2-C、负载试点、P1 当前验收入口修正、P3。
- [2026-11-12 工作区交付目录](2026-11-12/)：P3-R、P4。工作区日期是起始日期，实际完成日期见各报告，P4 完成于 11 月 18 日。
- [本次归档核验结果](verification.json)：历史清单、冻结来源与 ZIP 完整性。

## 大型 ZIP 的精确还原

GitHub 普通 Git 单文件限制为 100 MB。P3-R、P4 原始复现 ZIP 按 32 MiB 分卷，不重新压缩，不替换为 Git LFS 指针。`catalog.json` 记录有序分卷的大小和哈希、原包大小及完整 SHA-256；所有分卷与代码均在同一个 Git 仓库中。

在仓库根目录，仅核验全部交付材料（不写入归档、不运行算法）：

```bash
python experiment_runs/scripts/verify_delivery.py
```

核验并将两个原始 ZIP 还原到自己指定的目录：

```bash
python experiment_runs/scripts/verify_delivery.py --restore-dir /path/to/restored
```

Windows 示例：

```powershell
python experiment_runs/scripts/verify_delivery.py --restore-dir .\restored
```

输出位于指定目录的 `2026-11-12/` 下，原名分别为 `P3R_reproducibility_package.zip` 和 `P4_reproducibility_package.zip`。还原脚本会拒绝覆盖不同内容的既有文件。

原 ZIP 是历史独立复现包，P3-R 包内部以 `reports/`、`scripts/` 等为起点，P4 包内部以 `experiment_runs/` 为起点；解压前请核对目录结构。完整 Git checkout 已包含展开后的证据，日常读取不需要再还原 ZIP。

## 版本解释

原报告中的“未进入 P4”“尚未提交或推送”等是报告封存时的历史状态，保留原文以维持验收哈希。当前进度以 [总状态](../status.json)、[当前导航](../README.md) 和本次归档说明为准。`紧急规则修订与压力组提案_待确认.md` 同样保留历史文件名，其 A/B 提案随后已由用户批准；最终压力组实际取得 52 例，未擅自放宽到目标 100 例。

原 P3/P3-R 验收清单的相对路径起点不同：P3 以仓库根目录为起点，P3-R 和 P4 以 `experiment_runs/` 为起点。本次不重写这些清单或冻结代码。
