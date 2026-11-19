# P6 复现实验指南

## 证据与环境

从完整Git仓库运行，所有路径相对于仓库根。P4/P5原始分片、输入和原始源码必须保留。P6只做统计与只读复核，不运行新的在线性能实验。环境精确版本见environment.json；需要Python、numpy、pandas、matplotlib、scipy、pytest和可选PyMuPDF。原CP-SAT证书沿用已封存原生审计，不需要主机重装ortools。

建议单线程BLAS，避免统计矩阵并发干扰其它任务。Windows PowerShell：

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:PYTHONPATH=(Join-Path (Get-Location) 'experiment_runs/scripts')
$env:P6_OUT=(Join-Path (Get-Location) 'experiment_runs/reports/p6/P6-reproduction')
python -m pytest experiment_runs/tests/test_p6_statistics.py -q --junitxml="$env:P6_OUT/qa/unit_tests.xml"
python experiment_runs/scripts/prepare_stage6.py
python experiment_runs/scripts/analyze_stage6.py
python experiment_runs/scripts/sensitivity_stage6.py
python experiment_runs/scripts/oracle_stage6.py
python experiment_runs/scripts/audit_stage6_raw.py
python experiment_runs/scripts/review_stage6.py
python experiment_runs/scripts/plot_stage6.py
python experiment_runs/scripts/report_stage6.py
python experiment_runs/scripts/accept_stage6.py
```

prepare_stage6.py默认要求分析父提交；在交付后的提交上重现时用环境变量P6_ALLOW_DELIVERED=1，仍从固化父提交读取历史对象清单。不要覆盖已有P6封存批次。Linux对应export环境变量并使用同一脚本。

图表可选`--qa-tools <nature-figure审核脚本目录>`生成技能标准的字体/碰撞QA；不提供时仍可完全重画，输出单图对齐N/A记录。本次交付保留真实审核结果和人工图像复核说明。精确字体可能随系统替代改变，数值CSV和抽样计数应完全一致；PDF/PNG/gzip包头/环境及运行时间不要求字节级重现。

新目录中执行accept_stage6.py前，需对新渲染图完成PDF字号/碰撞QA，并写入新的figures/visual_review.json，不能把旧图的视觉审查直接当新图通过。上方命令中的plot_stage6.py若没有传--qa-tools，只完成绘图与数值复现，验收会明确缺少新QA而停止。本交付目录中的九图已经实际完成上述审查。

单因素2,280个独立原始分片可用`python experiment_runs/scripts/parallel_audit_stage6.py`四进程复核；它完整覆盖同一批输入，合并时检查分区无交集、分片2280和调用99840。其它阶段保持顺序复核，或在单因素已生成COMPLETE后运行audit_stage6_raw.py跳过已通过阶段。并行的是只读审计，不是在线方法计时。

## 独立核验

验收脚本校验所有消费来源SHA256、原历史科学文件对象、573200条原始评分/发布表对应、互斥失败归因、10000重采和完整比较范围、P4点估计重建、单位测试、图源和验收清单。重现的统计表按数值比较；完整重复数组为float32存储，百分位区间由float64原值计算。resampling记录整数抽样频数；轨道层按层原样本量归一，避免组大小随机改变层权重。

每个总体/分层/条件都保留适用/有效输出分母及未定义重采次数。只重采实例的区间用于条件敏感性，不替代轨道组先抽的主区间。仅两个测试卫星组及一个组的迁移无法支持广泛轨道组总体推断。A9离线选择结果冻结后仅作乐观描述。

## 取消项

P4-M/P5-M按用户决定排除；相关容器已停止并移除。本地未跟踪残留的删除被自动审批拒绝，不把它们纳入Git或复现依赖。原P5单因素N500/N1000继续保留。
