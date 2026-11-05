# P1 公开验收入口修复：更新 P2 后的当前版本

日期：2026-11-05（Asia/Shanghai）。性质：验收工具维护，不是新实验阶段；P3未启动。

## 结果

P1当前公开入口已更新为`verify_p1_current.py`，版本`1.0-post-P2`，在完成P2及其补充实验后的仓库中完整通过。当前入口说明见[P1_CURRENT_ACCEPTANCE.md](../P1_CURRENT_ACCEPTANCE.md)。原P1科学源码、实例、轨道窗口、参考计划、冻结协议和历史验收记录不变。

## 问题原因与修复

旧P1验收把`experiment_runs/README.md`、`STAGES.md`和`status.json`的P1内容哈希记入清单。后续正常更新P2状态后，这三个当前文件与P1历史哈希不同，旧入口因此在最后的清单检查报错。这是文件版本处理问题，不是试点数据或几何错误。

`verify_p1.py`本身也被P2原验收清单冻结，因此保留旧源码，新增当前入口，避免造成P2和补充证据链失效。当前入口保留旧入口全部科学检查，新增明确的历史到当前版本核对，未跳过不匹配项，也未更新旧验收值。

严格规则如下：

- P1原验收清单本身SHA-256固定为`25d426eadd00c91cee71f2ddc12df81b5a2ce2cb95e3799c0946dba28dbd3b40`。
- P2原验收清单SHA-256固定为`eb0e6ff6efcedc3b7e4bb8bca7416b5fefeda53de783d1b67c0d0b3e956fe987`。
- P1清单中19个不可变文件继续按原字节核对，完整科学源码与产物另按原运行清单检查。
- 只对上述三个进度文件作版本衔接：P1 Git提交`f8cd6afd8a8a33d43c9f178ae186bf42f9de18dc`中的内容必须匹配P1验收值；当前文件必须匹配P2验收值，且与P2提交`0a1b49434a33451880a4968b02ddfda90b6a0ab0`中的内容一致。
- 三路径列表固定，不能把科学文件加入豁免列表。若将来再次修改进度文件，应另行显式升级协议，不能将任意新哈希自动视为合法。

版本配置见[协议JSON](../protocol/P1_CURRENT_VERIFICATION.json)。原入口依然保存历史P1规则；当前公共复核使用下面的新入口。此次没有改写原README、STAGES、status或旧阶段报告。

## 当前验收命令

从完整Git仓库根目录执行，使用安装了冻结依赖的解释器：

```powershell
experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/verify_p1_current.py experiment_runs/reports/p1/P1-20261105T110427Z
```

写新的当前验收记录时显式指定新路径：

```powershell
experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/verify_p1_current.py experiment_runs/reports/p1/P1-20261105T110427Z --write-acceptance experiment_runs/reports/p1/P1-current-check-new/verification.json
```

输出路径只能在reports/p1内、位于原历史批次之外，拒绝覆盖已有记录。无需下载轨道快照或读取原始GP；公开派生数据足以进行本命令的检查，但不将窗口比较复算冒称原始轨道重新传播。

## 验证

当前入口完整重检通过：640个唯一轨道对象，384/128/128的对象划分及两两交集0；150个试点计划；150个任务/日历种子重建；50个D1接触重建；100个5s/1s窗口比较复算；全部原冻结源码、输入和产物哈希检查。当前入口输出中的`pytest_passed=125`明确指P1原批次冻结的125项测试证据，不是当前代码库测试数。

当前回归为**179项全部通过**，其中新增8项验收完整性测试，覆盖合法P1到P2进度迁移、四种文件篡改拒绝、P1/P2历史blob不符拒绝、验收清单缺失进度路径拒绝。使用工作目录内的独立临时测试目录，不依赖不可访问的系统pytest临时缓存。

本轮同时确认原P2复核仍可通过；原P1/P2及全部补充验收清单的文件字节未因本修复改变，所有新增内容限制在experiment_runs目录。修复未调整模型、算法、数据分布、参考计划或方法性能结果。

本轮执行结果、完整测试日志、源码提交及文件哈希保存在`reports/p1/P1-current-entry-fix-v1/`。当前版本验收记录`verification.json`分列历史与当前进度哈希；最终修复验收`acceptance_manifest.json`记录新入口、协议、测试及报告的哈希。
