# P0 阶段报告：离散 ISL 实现与正确性验收

完成日期：2026-11-05（Asia/Shanghai）。阶段结论：**P0 已完成，P1–P6 未启动。**

本报告对应用户指定的 P0：登记原代码缺失，实现离散 ISL、独立校验、参考规划、三类扰动、固定 PALR 与基础基线，并验证关键边界。实现身份为基于论文和完整实验方案的重新实现，不是恢复的原作者代码，也不是 HIST 精确复现。

## 1. 本阶段产出与验收结论

| 用户要求 | 已完成内容 | 验收结果 |
| --- | --- | --- |
| 登记原代码缺失 | 原算法、生成器、种子、参考计划/事件、日志、权重、环境逐项登记；保留证据路径与仓库基线提交 | 完成 |
| 离散 ISL 模型 | 固定端点、单跳、固定速率、整数秒、1 s 建链、双方半双工终端、外生日历、有方向单窗口传输 | 完成 |
| 独立完整计划校验器 | 单独复算时长、任务窗口、接触窗口、资源、日历、冻结、取消、邻域外保持及累计预算；重放每个接受状态 | 完成 |
| 参考规划 | 精确效用密度排序、deadline/ID 并列、最早可行插入；保存排入数、占用、空闲段与独立构建耗时 | 完成 |
| 三类扰动 | PCG64 独立事件种子；取消、紧急插入、奖励更新；冻结保护、N/A、更新后奖励共享 | 完成 |
| 固定 PALR | w=5/B=2，原索引对称邻域、保留/单项替换/插入、服务优先词典序、已验证 incumbent 与累计接纳账本 | 完成 |
| 基础基线 | Minimal-Repair、Frozen-Greedy；共用模型、硬约束、计时与预算上限规则 | 完成 |
| HIST 差异 | 原模型/缺失项与新 ISL 的资源、窗口、时长、邻域、种子、指标差异已逐项说明；未伪造历史结果 | 完成 |
| 正确性检查 | 115 项 pytest 全部通过；36 条输出计划再次独立核验；单例重放的计划/轨迹一致 | 通过 |
| 版本与环境追溯 | 协议、代码提交、17 份源码/配置哈希、依赖锁、实际硬件/环境、8 份原始产物哈希和复核记录 | 完成 |

本轮所有新增和修改均限于 `experiment_runs/`。与目录初始化后的基线提交比较，目录之外的原有文件无改动；原有 7 份归档材料的完整性校验通过。

## 2. 方法语义与已确认决策

实现契约见 [P0_IMPLEMENTATION_CONTRACT.md](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/protocol/P0_IMPLEMENTATION_CONTRACT.md)，原始工件登记见 [original_artifacts.json](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/protocol/original_artifacts.json)。

用户已确认的重要细化为：多取消取受影响原计划索引的下中位数；奖励变化优先取已排变化项索引的下中位数，若全部未排，则由可行开始区间中点映射到原计划位置；无窗口回退首个可编辑位置。没有将多取消邻域改为并集，没有扩大原方案的单邻域自由度。

其他实现细化公开如下：

- 时长为 `1+(D+R-1)//R`，避免浮点误差；接触窗口内缩为整数秒。任务窗口输入必须已离散化。
- 全部计划按 `(start,id)` 保存，冻结字段逐项保持；接收、发送与反向角色共用一个半双工终端。独立的两个短接触窗口不允许累计容量。
- 奖励抽样数量采用 `ceil(0.3*n)`；奖励及紧急效用必须为整数，必要时采用 ties-to-even 舍入，并在契约中声明。
- PALR 仅能单项替换 E 内未冻结任务，候选遍历按 ID；严格并列保留先遇到者。E 外保留任务不移动，原计划索引不随编辑变化。
- B 统计接受为 incumbent 的累计新增操作，包括紧急项与替换新增项；枚举但未接受的候选不计接纳。移除后再接纳同一新任务重新计数。最终 N_add 单列，不能替代累计预算。
- Frozen-Greedy 先尝试紧急项，再按效用密度重建未冻结任务；构建中的有效前缀作为候选，保留已验证且词典序更好的 incumbent，允许回退共同基准。
- 对外生窗口失效，区分“未冻结项必须移除”与“冻结承诺发生冲突”；两者分别记账。P0 只使用错误注入边界输入，未运行 P5 窗口扰动研究。

## 3. 正确性检查覆盖

正式记录：[pytest 文本](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/reports/p0/P0-20261105T102554Z/pytest.txt)；[JUnit XML](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/reports/p0/P0-20261105T102554Z/pytest.xml)。结果为 **115 passed**。

| 检查组 | 覆盖的关键行为 |
| --- | --- |
| 冻结 | 删除、起止移动、端点/ID 变化被拒绝；冻结取消和窗口丢失返回 frozen_conflict；全冻结时可利用真实空闲接纳紧急项但不改变承诺 |
| 双端资源 | 接收冲突、发送冲突、跨发送/接收的半双工冲突；双资源冲突分别计数并去重任务对；不同资源任务可并发 |
| 单窗口与方向 | 无窗口、反向窗口、窗口太短、两个短窗口累计均被拒绝；恰好结束于右边界合法 |
| 日历 | 双端忙区间均不可占用；与忙区间首尾相接合法；连续忙槽合并、实际负载与固定种子复现 |
| 输入与取整 | 非正速率/数据量、重复 ID、无效端点、非整数效用/时间等拒绝；大整数边界、非整除时长、窗口 ceil/floor 和冻结比例精确 floor |
| 预算与操作轨迹 | B=0 不接纳紧急项；紧急接纳计入预算；移除后再接纳不重置；伪造累计数、最终状态或不合法中间状态被识别 |
| 邻域与裁决 | 用户确认的下中位数和回退；E 外保持；奖励变化触发真实单项替换；紧急成功优先于更高的其他效用 |
| 超时 | 零预算/未验证输出不成功；中途截止保留已验证计划；最终校验超时仍 U_exec=0，不能算按时成功；分项和等于总计时 |
| 指标 | 外生取消与强制删除剔除；新奖励统一使用；全保留/可编辑移动分母区分；失败分母保留；可行与紧急服务成功分开 |
| 属性与独立性 | JSON 往返不变、任务/卫星改名不改变可行性、微型有限枚举的约束放宽单调性、60 组放置与逐秒独立枚举对齐、确定性方法复现、校验器无搜索模块依赖 |

微型有限枚举是约束单元检查，不构成 P2 的 CP-SAT 精确参照。CP-SAT 尚未实现和运行；它与启发式共用离散实例的模型对齐、最优/不可行证书将留给用户指定的 P2。

## 4. 人工微型案例联调

运行 ID：`P0-20261105T102554Z`。源码提交：`833829f562accd478c39586f076d6b935bf373a3`。实现版本：`0.1.0`；协议版本：`1.0`。

本次使用 **1 个人工构造的 4 星、12 候选任务微型实例**，不是 D1/D2 研究数据生成器。参考计划按规定的贪心规则建立；三扰动 × FR `{0,0.6}` × q `{0.2,0.8}` 构成 12 个事件，事件种子为 `100051–100062`。先执行 20 次微型案例预热，再记录 36 次正式方法调用。另有 1 次单例 CLI 重放，未作为新的独立事件并入汇总。

| 方法 | 适用事件 | 完整可行输出 | 按时且服务成功 | 紧急成功/全部紧急事件 |
| --- | --- | --- | --- | --- |
| Minimal-Repair | 12 | 12 | 10 | 2/4 |
| Frozen-Greedy | 12 | 12 | 11 | 3/4 |
| Fixed-PALR | 12 | 12 | 10 | 2/4 |

此表只说明接口联调和失败口径工作正常，**不能用于评价方法优劣、显著性、泛化或正式响应能力**。全部 36 个计划均合法并按本次预算输出，但部分未接纳紧急项，因此“可行 36/36”不等于“服务成功 36/36”。未接纳的紧急请求没有被宣称为数学上不可行。

原始输入、参考计划、冻结项、逐事件输出、参数、账本、验证结果、计时分项和指标均保存在 [运行目录](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/tree/main/experiment_runs/reports/p0/P0-20261105T102554Z)。不从历史 PDF 表格反推或填入新数据。

## 5. 环境、版本与证据复核

实际环境记录见 [environment.json](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/reports/p0/P0-20261105T102554Z/environment.json)。

| 项目 | 实际记录 |
| --- | --- |
| 系统 | Windows 11，AMD64，系统版本 10.0.26200 |
| Python | CPython 3.14.0，experiment_runs 内独立虚拟环境 |
| CPU | Intel Core Ultra 5 125H，14 核/18 逻辑处理器 |
| 内存 | 33,832,394,752 bytes（约 31.5 GiB） |
| 核心依赖 | NumPy 2.3.5，pytest 9.1.1；完整 pip freeze 已保存 |
| 执行方式 | 方法无并行修复工作线程；未绑核，未控制频率策略，未固定底层库线程数 |
| GPU/容器 | 未使用 GPU；未使用容器镜像 |
| 计时 | perf_counter_ns；实测时钟分辨率 100 ns；包含最终完整校验 |

这些条件满足本次 P0 实际环境可追溯要求；**不声称已经建立方案建议的 Ubuntu 22.04/Python 3.11 单核正式评测环境**。本机微型案例时延不进入正式排名。正式环境和完整依赖栈尚需后续阶段实际安装、核验、冻结。

可追溯材料包括 [原始运行 manifest](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/reports/p0/P0-20261105T102554Z/manifest.json)、[独立复核 audit](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/reports/p0/P0-20261105T102554Z/audit.json) 和 [依赖锁](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/environment/requirements-p0.lock.txt)。复核确认：

- 17 份实现/测试/配置/契约源码哈希一致，8 份原始运行产物哈希一致。
- 36 条输出重新通过独立校验，其指标和时间分项重新计算一致。
- 单例重放与原记录的计划、操作轨迹及累计预算一致；真实计时不要求逐位相同。
- 除 experiment_runs 外原文件无变化。

运行 manifest 创建后补充的单例重放由 audit 单独记录哈希，不改写原始 manifest。新增的实验目录属性规则保留证据文件的原始字节，避免 Git 换行转换破坏已记录的 SHA-256。

## 6. 复跑入口

在仓库根目录，使用已安装 P0 依赖的环境执行：

```powershell
experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/run_p0.py
```

每次生成新的 P0 运行目录，不覆盖已有结果；该命令不会启动 P1。仅运行检查可使用：

```powershell
experiment_runs/.venv/Scripts/python.exe -m pytest experiment_runs/tests -q -p no:cacheprovider
```

核对本次记录的哈希、计划及指标：

```powershell
experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/audit_p0.py experiment_runs/reports/p0/P0-20261105T102554Z
```

单例 CLI 见 `experiment_runs/scripts/run_case.py`，支持保存的案例输入、方法、w/B、时间预算和独立输出文件。代码、配置和测试均在专用实验目录内。

## 7. 阶段停点与限制

**P0 的指定工作和验收已完成，本轮停在 P0。** 后续阶段由用户指定，不自动进入 P1。

本阶段没有下载公开轨道快照、生成 D1/D2 数据集、执行 CP-SAT 200 小事件、参数选择、学习训练、主测试、消融或统计推断。PUCT、ALNS、CP-SAT、规则/学习控制和 HIST 观测调度均未声称已实现或已复现。

当前通过的是模型、算法接口与边界正确性验收。尚无证据支持新增性能优越性、原论文数值复现、真实星间系统可靠性或硬实时保证。未来若发现实现缺陷，须在相应阶段记录修正及受影响结果，不能覆盖旧记录。
