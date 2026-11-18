# P5 离线验收中的调查记录

2026-11-18。此文件记录派生审计的修正；正式方法、冻结源码和原始计时分片均未修改。

首次 `satellite-p5-search-detail-precheck` 在核对同邻域元数据时退出 1。定位记录为 `P4-test-D2-O-0060`、scenario 7、PALR-local：完整响应 42.412138 ms，stop_reason 为 cooperative_deadline，filter_ns 与 repair_ns 为 0，trace 为空，输出与已验证 initial_plan 完全相同。该返回路径在验证基准计划后、建立 E 外保持项元数据前触发合作式余量检查，故 `unchanged_outside_E` 字段为空。独立重建的 48 个 E 外保持项实际全部存在，邻域中心和跨度也一致。

原审计“所有已验证输出的该元数据字段必须等于完整 E 外集合”的假设过强。修订审计只对以下同时满足的路径承认字段尚未初始化：PALR-local、合作式截止、空轨迹、未筛选/未修复、输出等于初始计划且等于原参考去掉取消项。所有记录仍须从输入独立重建 E，并验证实际输出保留每个 E 外原项和新任务候选资格。其余元数据不一致继续触发失败。实际个数及定位见 `local_domain_early_returns.json`；最终完整验收另见 `acceptance_details.json`。

该调查不将早停认作完成搜索，不改变线上截止或成功计分，也不修改原始元数据。失败预检容器及后续检查退出状态保留在 environment.json。

CP 原生证据预检发现两处派生分析脚本错误：锁定 OR-Tools 9.14.6206 使用 protobuf `CpModelProto`，不支持另一版本的 `parse_text_format` 接口；随后计划对比缺少 `canonical_json` 导入。已分别改为 `google.protobuf.text_format.Parse` 解析 `CpModelProto`/`CpSolverResponse` 并补全导入。修正后 100 个原生模型全部通过模型验证；响应均为 OPTIMAL，最优界等于目标，从原生 solution 提取的计划逐项等于封存计划，原独立 ISL 校验通过。未重新求解或改动任何模型、响应、参考计划和计时。失败预检容器及修订后检查退出状态均留档。

原监听审计每轮先取得单因素目录快照，再依次处理后续阶段；快照取得时正式单因素仍在生成，故正式运行结束后有 335 个后生成单因素分片尚未被该轮扫描到。原三路审计均已转至后续阶段时，固定这 335 个 ID 和哈希于 `audit/fill_manifest.json`，用四个不重叠离线工作清单调用相同独立原检查器补审。等待中的分析容器停止后重启一次，以加载“等待补审回执”的排程补充，避免最终串行 verifier 与补审重复写同一分片。最终 verifier 仍须遍历全部原始分片和哈希；原始性能记录未重跑或改动。
