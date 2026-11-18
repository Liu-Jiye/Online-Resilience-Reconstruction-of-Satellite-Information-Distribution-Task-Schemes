# P3 环境预检报告：Linux 门槛未通过，阶段未完成

日期：2026-11-10（Asia/Shanghai）。状态：P3 已获授权；正式运行尚未开始。

## 已确认的执行范围

默认自然层 4000 训练＋1000 验证，按 D1 1600/400、D2-S 1200/300、D2-O 1200/300 分配；同一场景另生成 N500/h0.8 中竞争配对层，分别选参、分别报告。使用已批准的紧急候选规则 v2，不改变原单项替换算子。

实施 ET，最多 80000 条主层训练动作记录；配对中竞争层不追加训练标签。固定网格、规则一次验证调整、搜索参数与 ET 6 组验证阈值遵循方案。详见 `protocol/P3_APPROVED_SCOPE_V1.md`。

## 实际环境检查与失败

本机 Windows 已安装 WSL、Docker CLI 与 Docker Desktop，但初始 Docker Linux API 管道不存在，`docker version` 无法连接服务器。WSL 列表仅登记 docker-desktop，没有可直接使用的 Ubuntu 开发发行版。

已以隐藏窗口方式尝试启动 Docker Desktop。后端启动日志实际报告：

```text
starting services: initializing Inference manager:
listening on unix://<LOCALAPPDATA>/Docker/run/dockerInference:
remove .../dockerInference: The file cannot be accessed by the system.
(listener: The filename, directory name, or volume label syntax is incorrect.)
```

后端随后退出；未取得 Linux 服务端版本、可用镜像、Linux/Python3.11 运行环境或单核实验进程。诊断时 dockerInference 路径被登记为 ReparsePoint。这提示本地套接字或重解析点问题，但仅凭日志不能断定其根因，更不能宣称是算法、依赖或数据错误。

没有删除、重置或注销 Docker/WSL 数据，没有修改 Docker 全局设置。按用户刚确认的“建立 Linux 环境，失败先报告”约束，未切换 Windows 执行正式参数时延选择。

## 用户授权继续恢复后的排查

用户随后授权继续排查并恢复本机 Docker，先做可回退的残留套接字处理。

1. 单独改名 dockerInference 失败，返回“系统无法访问此文件”。
2. 将 `%LOCALAPPDATA%/Docker/run` 运行目录改名备份、重建空目录后重启；越过原故障，但后端随后因 `%LOCALAPPDATA%/docker-secrets-engine/engine.sock` 报同类错误而退出。原 run 及重试运行目录分别保存在 `run.p3-backup-20261110` 和 `run.p3-backup-20261110-attempt3`，未删除。
3. 对 Secrets Engine 目录普通 Move-Item 失败；.NET Directory.Move 返回 Access denied。没有修改 ACL、取得所有权、清空目录或读取秘密内容。
4. 使用 Windows CreateFileW、OPEN_REPARSE_POINT 与 BACKUP_SEMANTICS 标志只读打开 engine.sock，仍返回 Win32 1920，无法在当前进程中读取其重解析点元数据。未执行套接字删除。

失败的本轮 Docker Desktop 进程已停止，未保留新的失败重试后台进程。现有 Docker 镜像、容器、卷、WSL 发行版和磁盘均未重置。根因仍未确定；不能仅由这些错误推断升级 Windows 或 Docker 必定解决。

验证覆盖另已获用户确认：1000 验证基实例每例全部 12 情景、默认与中竞争层分别验证，固定网格共 720000 次调用；用户接受较长运行。尚未产生任何这些调用的正式结果。

## 数据与结果保护

原 P1 快照缓存和冻结分组仍可读取，后续仍应使用该快照及原始历元，不因当前日期变化而重新下载或修改 EPOCH。公开原始 GP 再分发限制保持不变；诊断包只记录文件哈希，不复制原始 GP。

P3 正式生成数 0，方法观测数 0，规则调整次数 0，ET 动作记录 0，训练模型 0，最佳固定参数／搜索参数未完成冻结。P4 未启动，测试性能未读取。当前预检报告不能替代 P3 完成报告。

## 恢复条件

恢复 Docker Desktop 后，应先确认 `docker version` 能返回 Linux 服务端，再构建 Linux/Python3.11 环境，核验实际亲和性、依赖与线程配置并锁定镜像摘要。在正式验证表现出现前，还须补齐并提交事件清单、选参聚合规则、一次规则调整的候选集合及失败停止条件。

如果本机 Docker 需要修复套接字、修改全局设置或重启系统，应由用户确定恢复方式；也可以使用用户指定的可访问 Linux 主机。环境恢复前不进行正式计时选参，不声称 P3 已完成。

当前需要用户先在本机交互环境修复／恢复 Docker Desktop Linux 引擎，或提供可访问的 Linux 主机。验收恢复的具体条件是 Docker 服务端可连接且可执行 Linux 容器；仅 CLI 存在或 Desktop 窗口打开不等于恢复。
