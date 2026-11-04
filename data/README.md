# 数据字段与来源规范

当前没有实验数据。`source_registry.csv` 是待填写的数据来源登记表；原论文文件在 `archive/`，不充当实验数据。

## 建议实例结构

| 对象 | 必需字段 | 约定 |
| --- | --- | --- |
| 实例元数据 | instance_id, seed, source_id, horizon_s, time_origin | 时间使用相对秒，绝对历元和时间标准另记 |
| 任务 | task_id, utility, task_windows_s, duration_s | ID 唯一、单位明确；任务价值来源标注 |
| 星间传输 | sender_id, receiver_id, data_bits, rate_bps, contact_ids | 固定速率时传输时长为 data_bits/rate_bps |
| 接触窗口 | contact_id, sender_id, receiver_id, start_s, end_s | 方向明确，窗口有来源及生成参数 |
| 参考计划 | task_id, start_s, end_s, resource_ids | 按开始时间排序，完整保存扰动前版本 |
| 冻结状态 | frozen_count | 前 frozen_count 项不可修改；不是百分比索引 |
| 扰动 | type, affected_task_ids, arrival_s, intensity, payload | cancellation/urgent_insertion/reward_update；保存修改后值 |
| 来源 | field_provenance | 每字段标记 observed/derived/synthetic |

观测任务和传输任务不能只靠标题区分；用 task_type 显式标注。多星并发需任务占用多个资源，不能只检查全局单序列相邻项。收发双端可用性与缓存/因果假设要说明。

## 数据生成的分层

1. 历史仿真：恢复原生成器与原种子，不可仅凭 50×100×5400 描述声称已复现。
2. 窗口扩展仿真：明确轨道/窗口生成规则、数据量、速率、卫星数量和任务分布；窗口充足/紧张/不可行的具体阈值在试验前定稿。
3. 公开资料派生实验：保留原轨道等资料，记录派生通信窗口的传播模型、遮挡和终端假设；任务效用、扰动与冻结字段可以明确合成。

同一实例在各方法间复用；轨道对象和时段隔离训练/验证/测试，避免学习控制泄漏。规模扩展和窗口组不能改变其他全部条件而使效应无法归因。

## 存储

原数据放 `data/raw/`，转换数据放 `data/processed/`，默认忽略以免误上传大型文件。正式数据发布时改为固定版本下载入口，附哈希、许可和生成脚本。仅通过合法允许再分发的数据生成匿名补充包。
