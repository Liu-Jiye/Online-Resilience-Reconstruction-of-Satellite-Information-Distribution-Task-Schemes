# 可追溯案例复核

选择顺序固定为P4及协议PHASES顺序，各阶段按基实例分片路径排序，取该类别首个原始记录，不按方法优势筛选。

| category | phase | base_id | scenario | method | status | total_ms | online_success | errors | source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| urgent_failure | P4 | P4-test-D1-0000 | 6 | Rule-PALR | feasible | 6.6554 | 0 |  | reports/p4/P4-20261117/main/P4-test-D1-0000.json.gz |
| cancellation_success | P4 | P4-test-D1-0000 | 2 | ALNS-ISL | feasible | 49.6791 | 1 |  | reports/p4/P4-20261117/main/P4-test-D1-0000.json.gz |
| window_or_receiver_counterexample | ablations | P4-test-D1-0007 | 11 | No-window | no_feasible_repair_found | 14.5499 | 0 | contact_window | reports/p5/P5-20261118/ablations/P4-test-D1-0007.json.gz |

完整输入、输出计划、修改轨迹和校验见raw_audit对应阶段examples.json；超时或紧急未服务不能单独证明物理不可行。
