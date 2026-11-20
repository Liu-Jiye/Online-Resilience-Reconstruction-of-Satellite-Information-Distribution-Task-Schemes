# PALR 自适应算子专项复跑

在 P4 封存的 1,000 个默认负载基实例上重跑每例的 12 个事件。P5 消融的 300 个基实例是其中的预定子集。排除小试使用的 216 个基实例，另行报告留出成绩。小试策略和实例清单见[冻结配置](../configs/palr_adaptive_rerun.json)。

每事件按固定种子打乱四种方法的调用顺序。每种方法预热 20 次，每个事件正式计时一次。四种方法均使用 50 ms 在线计时预算、w=5、B=2，以及相同的接触窗口、双端资源、冻结和词典序裁决。独立复核在在线计时结束后进行。

| 方法 | 配置 |
|---|---|
| 原固定 PALR | P5 修复内核，默认参数 |
| 缓存固定 PALR | 原固定内核，复用单次调用内的事件实例 |
| 优化固定 PALR | 复用事件实例和直接落位结果，固定使用验证择优算子 |
| 自适应 PALR | 复用事件实例，按事件类型和扰动强度选择落位复用、目标上界剪枝或按上界排序后剪枝 |

验收纳入全部适用事件，包括紧急任务未获服务以及超时的事件。相对原固定 PALR，至少一半的事件须快 10%，且全事件平均耗时须降低至少 10%。两项指标均使用配对簇 bootstrap 95% 区间下界，重采样 10,000 次。轨道层先抽轨道组、再抽组内基实例，保留原层比例。P4 全量、P4 留出、P5 消融子集和 P5 留出均须通过。逐次比较输出计划，另核对成功数、有效输出、超时和平均执行效用。

本次专项覆盖 P4 默认负载主测试样本、P5 默认负载消融输入和 P6 层级统计。其他方法对照、参数网格、负载和跨星座专项由其各自的封存报告记录。

```powershell
python experiment_runs/scripts/run_palr_adaptive_rerun.py run --output experiment_runs/runs/palr_adaptive_repeat
python experiment_runs/scripts/run_palr_adaptive_rerun.py summarize --output experiment_runs/runs/palr_adaptive_repeat
```

环境需有 Python 与 NumPy。正式材料同时记录运行环境、配置、来源代码及输入清单哈希，逐事件保存调用顺序、计划哈希、算子、计分与耗时。
