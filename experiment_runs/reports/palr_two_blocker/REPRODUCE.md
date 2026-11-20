# PALR 双阻塞补充实验复现

实验协议见 [PALR_TWO_BLOCKER_SUPPLEMENT.md](../../protocol/PALR_TWO_BLOCKER_SUPPLEMENT.md)。实际运行使用 Windows 11、Python 3.14.0、NumPy 2.3.5，单进程和系统默认 CPU 调度。Python 和 NumPy 版本、主机标识、计时边界见 `freeze.json`。复现无需轨道数据下载或外部求解器。

从仓库根目录执行下列 PowerShell 命令。输出目录由运行器创建，请提供新目录名。Linux 或 macOS 将第一行改为 `export PYTHONPATH=experiment_runs/src` 后执行同样的 Python 命令。

```powershell
$env:PYTHONPATH='experiment_runs/src'
python experiment_runs/scripts/run_palr_supplement.py palr-two-replay
python experiment_runs/scripts/summarize_palr_supplement.py palr-two-replay
```

运行器先生成并封存输入，然后预热，逐例跑机制样本、固定参数验证集和独立测试集。配置只用验证集选择。用 `--mechanism-only` 可在完成封存和两批机制检验后退出。在线计时基于本机墙钟，耗时分位、超时边缘样本及按实测效用选出的配置允许随复跑环境变化。机制的逻辑时钟回归断言，以及同一份归档原始输出的统计汇总，可确定性复查。新运行的 gzip 文件头可能含时间，`freeze.json` 的哈希对应每次归档实际字节。

直接从本轮归档重新生成表格的命令如下。

```powershell
$env:PYTHONPATH='experiment_runs/src'
python experiment_runs/scripts/summarize_palr_supplement.py experiment_runs/reports/palr_two_blocker
```

| 文件 | 说明 |
|---|---|
| `inputs/*.jsonl.gz` | 机制案例、验证和测试的生成输入。自然样本每行包含一个原计划及 12 个事件 |
| `*_rows.jsonl.gz` | 逐事件逐方法结果，包括工期、计划、操作轨迹、验证和失败状态。机制含逻辑时钟断言结果 |
| `freeze.json`、`policy.json` | 输入和运行源码 SHA-256、实际环境、仅由验证集确定的参数 |
| `natural_statistics.csv`、`paired_effects.csv` | 方法统计与 10,000 次按基实例配对重采样得到的区间 |
| `mechanism_statistics.csv`、`offline_grid_envelope.csv` | 机制分组结果和测试参数网格的事后潜力诊断 |
| `failure_review.csv`、`acceptance.json` | 失败类型与复核记录 |

`two-w5-B2` 为同参数新版固定 PALR，`selected-fixed` 为验证集择优固定的新版本，`adaptive-w`、`adaptive-B`、`adaptive-joint` 分别表示按事件类型选择邻域、接纳预算和两者。控制器在运行时只查已封存的配置。成功率分母为适用事件。条件效用只除以有效输出数。事后网格诊断取多次单参数运行中的最佳观测，因此也可能吸收运行时噪声。两方法的计划改动配对效应使用双方均交付有效计划的事件，成功率和 `U_exec` 的配对效应保留所有适用事件。

