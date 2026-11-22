# 10 ms 和 20 ms 下的紧急任务优先修复

紧急请求到达后，先检查能否把请求直接插入当前可行计划。如果有位置，使用原 PALR 接纳流程校验，并将该插入计入预算 B。随后用剩余时间执行候选搜索。在没有直接插入位置时进入原搜索流程。最终校验与完整调用耗时均计入响应预算。该规则使用已收到的请求。

## 配对回放结果

同一批 P5 的 300 个基实例、3,600 个事件在 Windows/Python 本机随机交错运行两轮。所有事件输入经 P5 归档哈希核对。表内仅统计紧急请求，2,400 次调用对应 1,200 个紧急事件乘以两轮。两组均用 w=5、B=2，按基实例配对重采样。

| 预算 | 固定 PALR | 紧急任务优先 | 成功率差（百分点） | 95% 配对区间（百分点） |
| --- | ---: | ---: | ---: | ---: |
| 5 ms（诊断） | 0/2,400 | 0/2,400 | 0.00 | [0.00, 0.00] |
| 10 ms | 24/2,400 | 182/2,400 | +6.58 | [+5.25, +7.96] |
| 20 ms | 455/2,400 | 460/2,400 | +0.21 | [−0.25, +0.71] |

10 ms 下两轮分别多成功 72 和 86 次，紧急调用 p95 为 10.83 ms。20 ms 下观测差异较小，区间跨零。该结果适用于本机离线回放，需要在目标环境验证时延。统计文件记录的是基于提交 `092a12d` 的完整回放。当时通过变换 P5 源码生成实验策略，其行为与仓库中的实验实现一致。

[逐调用统计](results.json.gz)

## 运行

从仓库根目录运行，`case.json` 使用现有 ISL 单例或列表格式，输出使用新文件路径。

```sh
python experiment_runs/scripts/run_case.py --case case.json --method Short-Budget-PALR --budget-ms 10 --output experiment_runs/short_budget_10.json
python experiment_runs/scripts/run_case.py --case case.json --method Short-Budget-PALR --budget-ms 20 --output experiment_runs/short_budget_20.json
python experiment_runs/scripts/run_palr_short_budget.py --output short_budget_replay.json.gz
```
