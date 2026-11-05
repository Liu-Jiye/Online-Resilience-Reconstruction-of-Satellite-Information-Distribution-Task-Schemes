# P1 公开验收：更新 P2 后的当前入口

当前入口版本：`1.0-post-P2`。用于在已完成 P2、紧急补充及 P2-C 的当前仓库中复核原 P1 试点。

在仓库根目录运行：

```powershell
experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/verify_p1_current.py experiment_runs/reports/p1/P1-20261105T110427Z
```

Linux或其他Python环境可将解释器替换为安装了冻结依赖的`python`。需完整Git仓库，保留P1和P2历史提交；不下载新轨道数据，不需要读取本地原始GP。该入口重建150例任务/日历、50例合成接触，复算100例窗口比较并检查划分隔离和全部计划。它不声称从原始GP重新传播轨道。

旧P1报告中的`verify_p1.py`是冻结的历史入口，其自身哈希也已纳入P2验收。当前公开验收请使用本页命令；旧源码及P1/P2验收证据保留，以免修复P1时破坏其他批次的追溯链。

## 当前版本如何核对历史证据

旧入口要求当前README、STAGES、status仍保持P1内容；这三个文件已正常更新为P2状态，造成历史文件与当前文件的哈希冲突。当前入口不跳过这些文件：

1. 所有P1科学源码、输入、产物和旧复核源码继续按原哈希严格校验。
2. 三个进度文件的P1历史Git内容必须匹配P1原验收值。
3. 当前三个文件必须匹配P2原验收值，且与P2历史Git内容一致。
4. 只允许这三个指定路径进行上述版本衔接；其他文件的改变仍立即失败。未来再修改进度文件需显式更新版本协议，不能任意放宽。

历史P1与P2验收清单本身也按固定SHA-256校验。配置见[当前验收版本协议](protocol/P1_CURRENT_VERIFICATION.json)。

## 保存新的当前验收记录

```powershell
experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/verify_p1_current.py experiment_runs/reports/p1/P1-20261105T110427Z --write-acceptance experiment_runs/reports/p1/P1-current-check-new/verification.json
```

输出路径必须在`reports/p1/`内，且位于原历史批次之外；已有记录拒绝覆盖。新记录明确分列P1历史哈希、当前P2哈希、对应历史提交及本次科学检查结果，不覆盖`P1-20261105T110427Z/acceptance_manifest.json`。

本轮修复报告见[当前入口修复报告](reports/P1_CURRENT_ENTRY_FIX_REPORT.md)。本轮未重生成科学实验，不启动P3。
