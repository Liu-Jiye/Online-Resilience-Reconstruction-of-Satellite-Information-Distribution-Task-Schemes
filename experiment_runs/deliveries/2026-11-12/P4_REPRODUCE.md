# P4复现

在experiment_runs目录下，使用environment/p3/Dockerfile和requirements.lock.txt建立同依赖Linux Python3.11环境，CPU0且OMP/OPENBLAS/MKL/NUMEXPR线程数均1。原正式镜像摘要见environment.json。

只重建主表与独立验收：python scripts/finalize_p4.py。该脚本将从原始main/timing分片重建CSV/JSON/报告初稿；人工解释附录保存在随包P4_REPORT.md，应保留引用。finalize脚本不会再执行在线方法；其创建的报告和验收清单哈希随离线重建而变化，不代表原始结果变化。

重新开展性能复测应复制原始归档到只读位置、在独立输出目录修改路径后建立新的source_freeze，明确是新复测，禁止覆盖本次封存证据。原入口run_p4.py只核验和跳过已完成分片，不将断点恢复冒充复测。

P3训练manifest和第一训练基实例归档随包，供20预热重现；train_p3r.py是独立回放函数的导入依赖，不会在finalize中训练模型。历史P3/P3-R完整数据不重复打包，historical_integrity.json记录既有验收清单哈希与核验总数。原轨道快照资格数据和组清单随包，不重新下载。
