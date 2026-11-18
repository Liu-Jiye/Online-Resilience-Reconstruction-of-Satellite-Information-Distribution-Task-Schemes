# P5 复算与复跑

本目录是 `P5-20261118` 的封存交付。每个批次的 `source_freeze.json` 固定实际方法源码、输入子集和参数；`acceptance_manifest.json` 固定所有交付文件。所有时间和质量结论以完整调用、独立严格校验后的记录为准。P6 未启动。

## 环境

- Docker image: `satellite-p3:20261110-locked`
- Image ID: `sha256:c465af02e860b05f063ca84b138e1cca72c235574b402937e6fb2eaf5d6ec728`
- Linux Python 3.11.18，依赖锁及镜像构建定义沿用 `experiment_runs/environment/`；当前版本、镜像与容器CPU约束见 `environment.json`。
- 正式方法仅在逻辑 CPU0 串行运行，数值库单线程。输入生成与独立离线审计使用其他逻辑CPU。宿主机/Docker/WSL调度可能造成抖动；本实验不保证硬实时。
- 容器工作目录 `/repo/experiment_runs`，设置 `PYTHONPATH=/repo/experiment_runs/src`；将仓库绝对路径挂载至 `/repo`。

## 只读复核与重建表图

在具有完整交付文件的仓库中，可使用同一锁定镜像运行下列命令。独立审计与分析不计在线时延。默认审计会复用已校验分片回执并再次核对文件哈希；若需要从原始证据重新进行全部独立重放，请在**仓库副本**中先将本目录 `audit/` 移至另一个备份位置，再运行审计，避免改动封存交付。

```bash
python scripts/audit_stage5_inputs.py
python scripts/verify_stage5_evidence.py
python scripts/summarize_stage5.py
python scripts/plot_stage5.py
python scripts/write_stage5_report.py
python scripts/audit_stage5_acceptance_details.py
python scripts/finalize_stage5_delivery.py
```

这些分析命令会重建派生文件，进行字节级复核时请在独立副本中使用；计时原始分片永不因重建而重跑。图中均值可复算，PNG/PDF的元数据不要求跨平台字节相同。历史导航文件的有意修改仅限README、STAGES和status，历史科学证据另由 `historical_bytes.json` 检查。

本次完整物理重放、CP原生证书检查和分析使用上述锁定Linux镜像。最终 `finalize_stage5_delivery.py` 的文件哈希、分母、清单及Git字节核验在Windows主机执行，以避免Docker绑定挂载逐文件检查的额外开销；主机Python/pandas版本及停止的离线清单检查容器记录于 `environment.json`。这一步没有重新求解或改变正式计时结果。

## 在新目录完整复跑

`scripts/reproduce_stage5.py` 保护本封存目录，只允许使用新的 `reports/p5/<run-id>`。所有命令在锁定Linux容器中执行；正式方法步骤使用 `--cpuset-cpus 0`。每次仅运行一个正式方法批次，不让两个CPU0方法批次重叠。先运行边界检查：

```bash
python -m pytest tests/test_p5_contract.py tests/test_p4_online.py -q
```

实际交付的预检JUnit见 `preflight_tests.xml`（24 passed）。

```bash
python scripts/reproduce_stage5.py prepare --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py inputs --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py ablations --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py searches --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py special --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py references --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py transfer --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py continuous --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py audit --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py summarize --out reports/p5/P5-reproduction
python scripts/reproduce_stage5.py plot --out reports/p5/P5-reproduction
```

正式连续实验前，设置 `P5_CONTINUOUS_PREFLIGHT=1` 运行一次continuous动作，确认训练轨迹预检通过后清除此变量。`run_p5_continuous.py` 为保留的第一版训练语义预检；正式实现使用 `run_p5_continuous_v2.py`，修正当前时刻恰好开始项的冻结并确保奖励仅从非冻结任务抽取。`semantic_continuous*` 是训练离线检查，不构成性能样本。

完整复跑会有不同的调度时延、合作式截止路径和搜索返回计划；不要求原始计时结果逐字节相同。输入列表、随机数种子、方法语义、分母和验收规则必须相同。阶段内探索性区间采用2000次条件基实例簇重采样，不替代P6的总体统计流程。

## 数据与结果解释

- `subsets.json`：300消融、100专项、50异常、60验证校准及迁移测试ID；抽样未读取方法结果。
- `inputs/`：单因素/窗口/异常的完整Case、变体元数据及哈希。N前缀、距离包含关系、因子隔离、参考计划和压力证书见 `input_independent_audit.json`。
- `ablations/`：47配置、169200正式调用；五个随机裁决种子和A10预算50ms重复配置独立保存。
- `tables/A9_per_base_selected_actions.csv`：按原方案每个基实例从25动作中离线选择一个动作，完整保留该动作的12事件；`A9_per_base_comparison.csv`与逐事件更乐观包络分开。两种选择都读取测试表现，不能作为在线算法。`acceptance_details.json`独立复核选择、升级中间计划与累计轨迹传递、同邻域候选资格。
- `calibration/` 与 `upgrade_threshold.json`：验证60基实例×12=720调用，仅选择升级触发阈值。
- `mechanisms/`、`simulations/`、`upgrades/`：分别为同E/B2机制、实际模拟量敏感性、共享50ms升级。不可混成全局操作排名。
- `single_factor/`、`windows/`、`anomalies/`：同派生输入上的正式输出。窗口组额外运行No-window/No-receiver诊断行；非法输出计失败。
- `references/initial_cp/`：100个初始参考CP-SAT原生模型/响应及状态；`references/inputs/` 为实际有效CP参考生成的事件。无可行CP参考时保留失败尝试，不以贪心代替。
- `continuous/`：完整方法私有状态轨迹；`tables/continuous_trajectories.csv` 独立复算交付效用、冻结和窗口错失，按轨迹统计。
- `tables/*_per_call.csv.gz` 保留种子行；`*_events.csv.gz` 为事件内种子均值；条件质量和全部事件执行效用分开。全局操作表明确复用P4原始证据，没有新增独立样本。
- `ipc/applicability_audit.json`：固定提交的40问题文件结构、哈希、20同编号对关系与适配能力；没有IPC性能结果。原始PDDL未再分发。

第三方轨道数据沿用既有来源和许可处理；P5距离实验只发布派生输入。IPC重新获取入口为 `scripts/audit_p5_ipc.py`，需设置指向仓库外缓存的 `P5_IPC_CACHE`，GitHub API可通过已登录 `gh` 读取；不得将令牌写入交付。
