# S03 PALR.pdf

自动提取文本，仅供搜索；公式、图片和表格请核对原文件。

## 原文件物理页 1

动态扰动下卫星任务计划的低干扰韧性修复
方法
摘要—计划感知局部修复旨在计划已下发、部分任务进入
操作协调链的条件下实现快速低干扰的计划修复，是支撑动态对
地观测卫星调度的关键而又具挑战性的技术。现有前沿方法多聚
焦于从零开始的静态规划、扰动后的全局重优化或稳定优先的最
小修复，却通常忽略了已下发承诺、扰动局部性与可控插入规模
之间的复杂耦合关系，导致保留任务被大量移动和可恢复效用被
错失。预测—反应式调度与冻结区间重调度所遵循的先承诺、后
局部修复原则，为已下发前缀约束下的计划修复提供了可能。因
此，我们提出计划感知局部修复方法（PALR），这是一种新的
把已下发承诺与扰动局部性作为硬约束的修复规则，其修复控
制要素包括冻结前缀硬保留、以扰动为中心的邻域编辑、显式插
入预算B 和词典序候选裁决，用于实现局部可控的低干扰修复。
然后，我们提出基于冻结前缀保持、扰动中心邻域编辑和预算控
制修复算子的局部修复流程，可在在线扰动响应下调节效用恢复
与计划稳定，提升低干扰快速修复能力。该方法通过联合利用冻
结前缀与可行性硬约束、邻域宽度与编辑范围、插入预算与效用
恢复之间的关系，提升效用恢复并保持计划稳定。统一协议下的
对比与消融实验表明，PALR 在保持与贪心全局重优化相当效
用的同时显著降低修复干扰成本；与最强基线相比，其插入任务
负担由0.539 降为0.335、减少约37.8%，修复时延由0.413
毫秒降低至0.084 毫秒。
Index Terms—对地观测卫星调度，已下发前缀修复，低
干扰重调度，计划感知局部修复，在线计划恢复
I. 引言
在计划已下发后的扰动修复这一场景下，对地观测
卫星调度领域已在观测选择、可见窗口匹配、机动约束
处理和多星协同上取得了显著成就。尽管现有调度方法
在静态计划构建、应急任务插入和全局重优化上表现优
异，但在计划已下发后的扰动修复这一核心任务上，仍
存在难以同时兼顾已下发计划保持、局部扰动响应和修
复效率等不足。也就是说，一旦计划进入操作协调链，
调度器面对的就不再是纯粹的效用最大化问题，而是既
有承诺约束下的修复问题。
现有研究采用了从多种角度推进对地观测调度的
总结性策略。根据已有成果，这些方法主要分为三类：
第一类是从零开始的静态规划，通过搜索、学习和数学
规划构造高质量计划，以达成静态场景下的效用最优，
但这类方法没有回答部分计划下发后应如何修复。第二
类是扰动后的全局重优化方法，即使扰动是局部的，也
会移动大量保留任务、重新打开操作方期望保持不变的
决策，缺失对已下发承诺的保护能力。而第三类是稳定
优先的局部修复方法，若实现得过于刚性，会把可恢复
的效用白白丢弃，缺失对局部可行紧急任务的吸收能
力。为了确保既保护承诺又不过度保守，本文关注把计
划稳定作为算法约束嵌入修复规则的核心能力，属于第
三类的改进方向。
当前在扰动修复这一场景下，更强的全局搜索会扩
大可编辑范围并抬高修复时延，而过度保守的稳定优先
修复则会浪费扰动新释放出来的空闲资源。这样的设计
没有把已下发承诺、扰动局部性和可控插入规模统一建
模的能力，反而在计划保持、局部响应和低时延三项需
求需要同时满足时暴露出短板。
为了避免这一困境，我们将研究核心确定为把动态
对地观测调度建模为已下发前缀约束下的局部可控修
复，而非全局重规划。即通过冻结前缀硬保留、以扰动
为中心的局部编辑和显式插入预算这三项控制，来在效
用恢复与干扰控制之间取得平衡。经过这样处理后的修
复问题，通过限定编辑范围并显式记账每一次改动，理
论上可以得到既可执行又低干扰的修复结果。图1直观
展示了全局重优化与PALR 局部修复在编辑范围和承
诺保持方式上的差异。
在追求低干扰快速修复这一核心需求的同时，扰动
处理面临着巨大挑战：修复往往受时间约束，需要在有
限时间内完成从扰动解析到可行计划输出的关键操作
链，并同时覆盖任务取消、紧急插入和奖励更新三类扰
动，面临计算资源和响应时延的严格限制。
为了解决上述问题，我们参考了预测—反应式调度


## 原文件物理页 2

图1. 全局重优化与PALR 局部修复的概念对比。全局重优化会重新打开已协调决策并形成较宽的编辑足迹；PALR 保持已下发前缀，仅在扰动邻域内执行
受插入预算约束的局部编辑。
和冻结区间重调度的思路，即先冻结计划的一部分、把
编辑限制在局部区域、再用稳定性来权衡效用。该思路
中“先承诺、后局部修复”的原则与本文追求的低干扰
修复目标一致。基于这一思路的启发，我们构建PALR
修复规则，并通过邻域裁剪与预算控制加以约束，从而
达到局部可控的快速修复能力。具体来说，冻结前缀硬
保留机制通过把已下发的前缀标记为不可修改来保护
承诺，并收集飞控与地面协调约束作为硬约束。其次，
以扰动为中心的邻域编辑机制扮演限制干扰扩散的角
色，其可编辑范围是通过围绕扰动边界设定邻域宽度得
来的，并由插入预算B 指导新任务接纳规模的控制。
与直接把扰动后状态当作新规划实例的现有方法
不同，PALR 可以在保持已下发计划不变的前提下完成
局部修复。PALR 所研究的低干扰修复的重点在于把冻
结前缀有效性和插入预算提升为一等的、可审计的量，
这与仅在优化后才评估稳定性的传统方法存在本质区
别与创新。综上所述，我们在本研究中的贡献如下：（1）
我们把动态对地观测调度形式化为已下发前缀修复问
题，使冻结前缀保持、效用恢复和干扰控制被联合评估，
而非仅由静态目标值衡量；（2）我们提出PALR 修复
规则，将显式冻结前缀处理、有界可编辑邻域和作为可
解释控制变量的插入预算B 统一在一条可审计的修复
路径中；（3）我们在统一的对地观测调度实验协议下给
出考虑方差的实验证据，通过与贪心和基于搜索的重规
划基线的多指标比较，刻画了有界局部修复的适用区间
及其已知的退化和升级边界。
本文其余部分安排如下。第II 节将本文置于对地观
测调度规划与重调度修复的背景中加以定位。第III 节
定义系统模型、协议边界、形式化修复问题与设计需求。
第IV 节给出PALR 规则及其形式化性质。第V 节报
告实验证据。
II. 相关工作
A. 对地观测规划与预测-反应式重调度
近年来，对地观测卫星调度取得了显著进展，带来
了更高的计划质量与更强的约束处理能力。与此同时，
分布式约束优化、在线应急调度、图引导搜索与约束
规划的提出进一步拓展了对地观测调度的静态效用上
界[1]–[6]。从头构建的规划器通过在候选观测集合上进
行搜索、学习和数学规划实现了高质量的静态计划[3],
[5]。从静态规划出发，更复杂的框架如分布式任务规划、
周期性星上重调度、变尺度深度强化学习调度器与双层
优化模型进一步扩展了动态响应能力[7]–[11]。在对地


## 原文件物理页 3

观测之外，制造与生产领域把重调度视为效率与稳定性
的权衡，多目标重调度综述、深度强化学习动态调度综
述与数字孪生驱动调度综述为已发布计划的可问责修
复提供了相邻的方法背景[12]–[14]。然而，上述对地观
测方法主要依赖从零构建或全局重优化，面临已发布承
诺缺乏显式保护，并且缺少可见窗口、机动可行性和冻
结前缀审计等对地观测专有结构的建模。此外，有界扰
动模型与修复成本权衡等方法通过限制单次重调度的
改动幅度，以有效缓解上述可问责性缺失[15], [16]。这
些方法的基础是把稳定性作为一等约束或权衡目标，其
对修复足迹的关注为已下发前缀约束下的修复提供了
启发，也启发了本文把冻结前缀与插入预算提升为一等
硬约束的研究思路。
B. 学习引导的破坏与修复
学习引导的大邻域搜索的兴起推动了自适应局部
修复的发展，用户期望在受扰的组合优化实例上获得
更高质量与更强迁移能力的修复[17]–[23]。大邻域搜索
也被应用于经典调度问题，如公交司机排班[24]；而混
合整数规划的学习式加速（如学习式后门变量）与多智
能体强化学习中的大邻域思想则从不同角度拓展了这
一方法族[25], [26]。然而，开放式构造与改进倾向为
已发布计划修复带来挑战。在承诺保持约束下，学习
引导的局部修复是一种实用的解决方案。可迁移局部
策略、记忆增强强化框架与跨问题迁移方法通过学习
邻域控制平衡了搜索质量与迁移需求[27]–[31]；面向大
规模路由的全局划分加局部构建、基于扩散的神经求
解器与抽象约束规约上的局部搜索进一步丰富了求解
器设计[32]–[34]；面向卫星的局部注意力神经重规划器
通过局部化建模提高了单星敏捷光学卫星调度的适应
性[35]。这类基于图的组合优化与搜索控制方法的更广
背景可见于相关综述与树搜索实践[36]–[38]。这两类方
法都体现了自适应局部修复的趋势，以确保受扰后的高
质量恢复，尽管学习式邻域控制偏向搜索质量与迁移，
而卫星神经重规划器偏向领域专有结构，二者有所不
同，但都忽略了冻结前缀语义与可审计的扰动权衡。本
文提出的方法通过把冻结前缀保持、局部邻域编辑与显
式插入预算组织为一条可审计的修复流程，针对上述局
限系统解决已发布计划修复中承诺保持与低干扰响应
难以同时满足的问题。
III. 系统与问题建模
A. 系统概述
我们沿用已有工作的对地观测调度任务形式化：一
颗敏捷卫星需要为超额认购的候选观测集合安排计划，
每个观测都带有可见窗口、效用值，以及由机动和时序
行为引出的可行性约束[3]。计划由一串按时间排序的
被选观测构成。在动态场景下，调度器收到的是一个任
务集合连同一份既有计划，而这份计划的前缀可能已经
被操作方使用。
设P = (o1, . . . , om) 为扰动前的参考计划，k 为下
发后第一个可编辑位置。前缀F = (o1, . . . , ok−1) 被视
为冻结部分，后缀(ok, . . . , om) 仍可编辑。扰动描述子
d 指定需要吸收的改变：某个已排任务可能被取消，某
个新的紧急任务可能到达，或者效用发生更新。修复问
题要求给出一份新的可行计划P ′，它保持F 不变、满
足对地观测约束，并在效用与干扰之间取得可辩护的折
中。
修复工作流分为两个阶段。首先，初始规划器为当
前任务集合生成一份参考计划。其次，一旦该计划的一
部分被视为已下发，扰动发生，修复模块被调用。修复
模块必须考虑已承诺的计划，判断剩余后缀中有多少需
要解锁，生成局部候选编辑，并足够快地返回一份新的
可行后缀以供在线使用。这一工作流与普通的静态重规
划有本质差异：规划状态现在包含先前已承诺的决策、
扰动类型和剩余的自由度，因此修复算法必须跟踪计划
语义，而不仅仅是目标值。一个忽略冻结前缀的方法在
朴素效用记账下可能看起来很强，但因为它使已协调好
的工作失效而在操作上不可接受。
B. 形式化问题定义
1) 任务与计划表示: 一个观测任务是一个元组o =
(wstart, wend, u, θ)，其中[wstart, wend] 是卫星可以对目标
成像的可见窗口，u ∈R+ 是效用值，θ 编码几何与操
作约束（例如侧摆角限制、下传要求）。记候选任务集
合为O。一个计划P = (o1, o2, . . . , om) 是一串按时间
排序的被选观测，其中oi ∈O 且每个任务至多出现一
次。计划的效用为U(P) = ∑m
i=1 u(oi)。
2) 可行性约束: 计划P 是可行的，当它满足：
• 可见窗口约束：每个观测oi 必须安排在其窗口内：
ti ∈[wstart(oi), wend(oi)]，其中ti 是oi 在P 中的
开始时间。


## 原文件物理页 4

• 机动间隔约束：相邻观测之间必须留出足够的时
间供卫星在目标之间侧摆。形式上，设∆(oi, oi+1)
为oi 与oi+1 之间的最小侧摆时间，由二者的角度
间隔和卫星的侧摆速率上限算出。我们要求ti+1 −
(ti + dur(oi)) ≥∆(oi, oi+1)，其中dur(oi) 是oi 的
成像时长。
• 不重复约束：每个观测在P 中至多出现一次。
若所有约束都成立则记feasible(P) = 1，否则记
feasible(P) = 0。
3) 已下发前缀约束下的修复问题:
设P
=
(o1, . . . , om) 为扰动前的参考计划。计划部分下发
后，前k −1 个观测已承诺、不可修改。我们称
F = (o1, . . . , ok−1) 为冻结前缀（或已下发前缀），
S = (ok, . . . , om) 为可编辑后缀。一个扰动d 指定对
任务集合或效用的一处改变：
• 取消：某个已排任务oc ∈S 变得不可用，必须移
除。
• 紧急插入：一个新的高优先级任务ou /∈P 到达，
可行时应予以容纳。
• 奖励更新：部分任务的效用发生改变，需要调整计
划以捕获新的价值。
修复问题寻找一份新计划P ′，使得：
max
P ′
U(P ′)
(1)
约束条件为：
P ′[1 : k −1] = F （冻结前缀保持）
(2)
feasible(P ′) = 1 （对地观测约束）
(3)
在效用相当的计划中，修复进一步偏好更小的任务集合
改动（增删观测的数量）、更低的插入负担（新增任务的
数量）和更小的时间偏移（保留任务的总计划移动）。因
此，效用与干扰是问题定义的一部分，而非事后诊断。
4) 局部性与以扰动为中心的邻域: PALR 的一个
关键设计选择是把编辑限制在一个以扰动为中心的邻
域内。设pos(d) 表示受扰动d 影响最大的计划位置（例
如被取消任务的下标，或紧急任务的优选插入点）。d 周
围宽度为w 的邻域定义为：
Nw(d) = {oi ∈S : |index(oi) −pos(d)| ≤w}
(4)
PALR 把局部搜索限制在Nw(d) 内，从而给修复引发
的干扰划定空间范围。Nw(d) 之外的观测在修复后的计
划中保持不动。
5) 插入预算控制: 为进一步限制修复强度，PALR
引入一个显式的插入预算B ∈Z≥0，用来给修复期间可
新增的任务数量设上限：
|P ′
new| ≤B
(5)
其中P ′
new = P ′ \ P 是新插入观测的集合。参数B 是
一个可解释的控制旋钮：较小的B 优先保证计划稳定，
较大的B 允许更激进的效用恢复。
C. 评测协议与复杂度
由于最接近的对地观测图神经搜索规划器的私有
资产不可得，我们在一套统一的、论文内部认可的协议
下评测所有方法，而不宣称严格复现[3]。该协议保留
了任务形式化、冻结前缀语义和所关心的修复指标，因
此所有绝对数值只作为协议内部的比较来解读。我们用
FR ∈[0, 1] 记冻结前缀比例：FR = 0 表示没有已下发
前缀，FR = 0.6 表示修复开始前参考计划的60% 已被
承诺。所有方法都在同一实例生成器上执行，采用匹配
的随机种子和相同的面向修复的指标集，因此时延被解
读为共享评测路径下的相对修复代价，而非端到端任务
系统时延。
精确修复问题在其自然判定形式下是NP-难的。当
FR = 0 且没有局部编辑限制时，它退化为静态对地观
测调度：在可见窗口和顺序相关机动约束下选择并排序
一个效用最大化子集。这一基础问题在对地观测调度文
献中已被公认为难解[1], [3], [6]。已下发前缀和有界修
复动作只会增添组合结构，而不会简化它。
D. 下发之后的失效模式与设计需求
已下发计划的对地观测调度并不是“静态规划外加
一个扰动”。扰动会在一个部分承诺的结构中传播：取
消会腾出局部空闲容量，这些容量是被利用还是被浪费
取决于修复方法；紧急插入同时向响应性与承诺保持两
个方向拉扯；奖励更新使拓扑结构保持不变，却打乱了
价值排序。这揭示了纯以效用为中心的比较中的隐蔽失
效模式——一个修复方法可能报告更高效用，却因依赖
大量保留任务移动、大规模插入级联或违反已下发前缀
而在操作上很弱。
上述分析指向面向可靠性的修复系统的五项设计
需求。
• G1：承诺保持。冻结或已下发的前缀必须被显式
建模；违反必须被报告，而不是被隐藏。


## 原文件物理页 5

• G2：低扰动适应。方法应使任务集合改动、插入数
量和被保留任务的时间移动保持较小。
• G3：快速响应。修复周期在计算上应显著低于更
重的全局重规划或搜索。
• G4：扰动覆盖。修复方法应在单一修复视角下处
理取消、紧急插入和奖励更新。
• G5：可审计行为。成功和失效模式应能通过显式
的局部编辑和可度量的实际后果得到解释。
这些需求正是本文方法直接评估的组件：把插入预算B
与冻结前缀有效性提升为一等的、可审计的对象。
IV. 方法：计划感知局部修复规则
A. 章节概述
本章节详细阐述我们提出的计划感知局部修复规
则（PALR 规则）：给定一份参考计划、一个扰动描述
符和冻结前缀边界，该规则输出一份修复后的计划以及
效用、扰动和有效性诊断，如图2所示。
B. 整体框架
基于“下发计划不能被随意改动、扰动响应应保持
局部”这一动机，以及“把承诺保持和插入规模都当作
硬约束”这一核心原则，我们提出了以有界局部编辑为
核心的PALR 规则。首先，针对“已下发前缀不可修
改”这一挑战，我们设计了冻结前缀保持机制；随后，
为解决“修复引起的移动会向远处传播”这一挑战，我
们设计了扰动中心邻域编辑机制；接着，引入显式插入
预算B 控制新接纳任务的规模；最后，三个机制通过
一条修复流程串联起来，其中前缀保持与可行性作为硬
约束、效用与扰动作为软目标，这样的选择使PALR 成
为一个修复方法而非通用重规划器。
C. 具体设计
模块1（冻结前缀保持）：该机制把已经进入操作
协同链的计划部分锁定，使修复不触碰这些已承诺的决
策，具体而言：
• 输入规范：参考计划P = (o1, . . . , om) 与第一个可
编辑位置k，其中前缀F = (o1, . . . , ok−1) 被视为
冻结、后缀(ok, . . . , om) 可编辑；
• 公式描述：硬约束要求
P ′[1 : k −1] = F,
(6)
其中P ′ 是修复后的计划，即前k −1 个观测在修
复后必须与原计划逐位一致；
• 输出规范：得到一个只在i ≥k 处发生变化的候选
计划，并满足冻结前缀逐位保持这一有效性标准。
该模块的输出（锁定的前缀和开放的后缀）作为输入传
递给模块2 和模块3。
模块2（扰动中心邻域编辑）：为了把修复引起的
移动限制在扰动附近，我们提出了邻域界定和局部候选
池筛选两个组成部分，在扰动为局部的场景下达到“只
重开必要后缀、其余保持不动”的效果。
• 组成1（邻域界定）：采用以扰动边界为中心、宽度
为w 的解锁窗口，因为只有落在该窗口内的位置
才被允许改动，形式上定义为
E(d, w) = {oi ∈P | k ≤i ≤min(m, b(d) + w −1)},
(7)
其中d 是扰动描述符，b(d) 是扰动d 触及的第一
个后缀位置，w 是邻域宽度；
• 组成2（局部候选筛选）：使用E(d, w) 覆盖的时间跨
度作为筛选条件，我们要求局部候选池Uloc(d, w) ⊆
U 只包含可见性窗口与该跨度或扰动释放的空闲
相交的未排任务，从而使规则先在扰动的因果边界
附近尝试吸收扰动，再考虑对后缀远处花费计算。
组成1（邻域界定）是组成2（局部候选筛选）的基础，
二者为顺承关系。该模块的输入来自模块1（锁定的前
缀），其输出（解锁邻域和局部候选池）传递给模块3。
模块3（预算控制的修复算子）：修复的算子空间
围绕保留、替换和插入三种动作组织，主要由以下三个
步骤依次组成：
• 步骤1（保留）：对邻域内每个未被取消且与已构建
部分相容的观测oi，将其按原位追加到P ′，该步
骤在不移动被保留任务的前提下恢复局部可行性；
• 步骤2（替换）：当邻域内某观测oi 可被局部候选
池中效用更高的oj 取代且替换后仍可行时执行交
换，形式上要求u(oj) > u(oi) 且feasible(P ′) = 1，
然后据此更新候选计划；
• 步骤3（预算插入）：最后，在插入预算未耗尽时贪
心地加入局部可行的新任务，具体来说，每次选取
obest = arg maxo{u(o) : feasible(P ′ ∪{o}) = 1} 并
计入插入计数，直到达到预算上限。


## 原文件物理页 6

图2. PALR 总体框架。方法以参考计划、冻结边界、扰动、候选池、邻域宽度和插入预算为输入，经冻结前缀保持、扰动中心邻域编辑与预算控制算子生成
局部可行候选，并按照可行性、效用和干扰指标进行词典序裁决，得到保持冻结前缀的修复计划。
三个步骤具有严格的顺承关系，前一步骤是后一步骤的
基础，需依次执行。该模块的输入来自模块1 和模块2，
其输出作为系统最终的修复计划。插入步骤受硬约束
|{ai ∈π : ai = Insert(·)}| ≤B
(8)
限制，其中π 是施加在邻域内的算子序列，B 是插入
预算。
D. 模块融合
为了应对“三类扰动需要在同一规则下统一处理”
这一挑战，我们提出了以词典序偏好统一裁决候选计划
的融合方式。由于效用恢复与扰动控制之间存在张力，
为了区分硬约束和软目标，我们定义了如下裁决顺序，
随后展开为一条修复流程：先拒绝任何改动冻结前缀或
违反可行性的候选，再最大化恢复的效用，然后依次最
小化任务集合改动、插入任务数量和被保留任务的时间
移动。
算法3 把上述流程形式化。它以参考计划P、冻结
边界k、扰动描述符d、候选池U、邻域宽度w 和插入
预算B 为输入，返回一份保持F = P[1 : k −1] 并满
足对地观测可行性的修复计划P ′。
段落总结：这种方法不仅能在取消场景下利用新释
放的空闲恢复效用，而且能在奖励更新下不移动被保留
任务地接纳新的高价值机会。由于前缀保持、局部邻域
和插入预算这三个机制可以合并进同一条流程，达成了
“默认使用低扰动局部修复、仅在必要时升级到更重搜
索”这一核心目标。数学上，插入预算B 是唯一经本
文验证的控制变量：B = 0 时方法退化为严格的稳定优
先基线，增大B 会扩大可接纳的插入集合，从而在效
用恢复与调度稳定之间调节修复强度。
E. 性质与边界分析
命题1 (前缀保持). 设F = (o1, . . . , ok−1) 是输入计划
P 的冻结前缀。对于每一个合法输入，PALR 规则输出
的修复计划P ′ 满足P ′[1 : k −1] = F。
a) 证明梗概。: 该规则只在可编辑后缀i ≥k
内构造候选。任何改动冻结前缀位置的候选都会在效用
排序之前被拒绝，剩余候选还必须通过可行性检查。因


## 原文件物理页 7

算法1：PALR 规则
输入: P (参考计划), k (冻结边界),
d (扰动), U (候选池),
w (邻域宽度), B (插入预算)
输出: P' (修复后的计划)
1: F <- P[1:k-1]
// 冻结前缀
2: S <- P[k:m]
// 可编辑后缀
3: E <- BuildNeighborhood(S, d, w)
4: U_loc <- FilterCandidates(U, E)
5: P' <- F
// 以冻结前缀初始化
6:
7: // 步骤1: 最小修复(恢复可行性)
8: for each o_i in E do
9:
if o_i != 被取消任务and Compatible(o_i, P') then
10:
P' <- P' union {o_i}
// 保留
11:
end if
12: end for
13:
14: // 步骤2: 预算控制的插入
15: inserted <- 0
16: while inserted < B do
17:
o_best <- argmax_{o in U_loc\P'}
18:
{u(o) : Feasible(P' union {o})}
19:
if o_best 存在then
20:
P' <- P' union {o_best}
21:
inserted <- inserted + 1
22:
else
23:
break
// 没有更多可行插入
24:
end if
25: end while
26:
27: return P'
图3. PALR 修复规则。算法保持冻结前缀F ，在局部邻域E 内恢复可行
性，并贪心地插入至多B 个新任务。
此每一个可接纳的输出都保持F。命题1 虽然基础，却
是本文可靠性论证的核心：严格的紧急插入成功只在修
复后的调度保持冻结前缀时才计为成功。
定理1 (NP 困难性). 动态对地观测卫星修复问题的判
定版本是NP 困难的。
b) 证明梗概。: 当F = ∅（没有冻结前缀）且
预算无限时，修复问题退化为静态对地观测卫星调度，
后者已被证明是NP 困难的[3], [6]。这一困难性结果为
使用像PALR 这样的有界启发式方法提供了依据，它
以最优性换取速度和可预测性。
命题2 (效用恢复的单调性). 对固定输入，增大插入
预算B 绝不会降低修复计划的效用：当B1 ≤B2 时
U(P ′
B1) ≤U(P ′
B2)。
该证明源于算法3中的贪心插入策略。然而，单调
性不推广到扰动指标：更高的预算会增加任务集合改动
和插入负担，这在实验中得到观测。插入预算B 因此
定义了一条实用的修复前沿——在B = 0 时PALR 退
化为最小修复，更大的预算则扩展局部恢复，但可能违
背低扰动的初衷。
这些结果也界定了当前的主张。在FR = 0 的紧急
插入下，PALR 在数值上与最小修复完全相同，因此该
规则尚不是一个更丰富的紧急放置机制，其被支持的角
色更窄：一个可信的取消修复和奖励更新修复器，并带
有一条有用的预算前沿。在重冻结前缀的紧急插入下，
带学习先验的PUCT 重规划器表明更强的搜索能在相
同硬冻结约束下恢复更多效用，但代价是更大的任务集
合扰动、更大的被保留任务移动以及约高两个数量级的
延迟。所有保持前缀的方法都在0.34 的严格紧急插入
成功率处饱和（50 个实例中的17 个），因此效用差距
应被理解为在相同的严格成功上限内的比较。被支持的
规则是：默认使用局部修复，仅当额外效用能够证明大
幅更高的延迟和移动是值得的时才升级。
V. 实验
A. 实验设置
所有报告的主要结果都使用单一被接受的、与论文
对齐的协议：50 个实例、每个实例100 个候选观测、规
划时域τ = 5400，并使用固定随机种子以保证可比性。
我们评估三类扰动：取消、紧急插入和奖励更新。扰动
在参考计划生成后施加，冻结前缀比例FR 控制在修复
开始前该计划已被承诺的比例。
为了更全面地评估本研究提出的PALR 规则的性
能，我们将其与两大类基线方法进行比较：全局重优化
与稳定优先修复两类基线。全局重优化类以贪心全局重
优化为代表，它是对地观测卫星中自然的全局规划基
线[2]–[6], [39]，愿意激进重开可编辑后缀；为加强与图
引导树搜索规划的比较，我们在相同的冻结感知修复框
架下报告两个推理期PUCT 对比方法——一个启发式


## 原文件物理页 8

PUCT 重规划器和一个带学习先验的变体，后者使用
40 次模拟、最大深度12、top-k 候选控制20、探索常
数1.5、浅层引导深度2，以对地观测卫星图神经树搜
索路线[3] 和标准蒙特卡洛树搜索实践[38] 为基础。稳
定优先修复类以最小修复为代表，它遵循较新的稳定优
先和有界扰动修复形式[12]–[16]；当稳健性问题受益于
额外的低扰动对比时，我们进一步纳入一个学习型局部
修复变体和一个算子策略修复变体[37]。学习先验行只
改变搜索先验、不改变修复契约，因此被用作有信息量
的对比方法，而非对完整图神经树搜索训练栈的复现。
实验通过以下四组指标评估保持承诺的修复质量：
效用衡量修复计划的总观测价值，用于评估效用恢复能
力；扰动组（任务集合改动、插入负担、被保留任务时
间移动）衡量修复引入的计划改动，用于评估低干扰能
力；延迟衡量共享评估路径上的相对修复成本，用于评
估快速响应能力；严格有效性衡量在保持冻结前缀前提
下的紧急插入成功率，用于评估承诺保持能力。这一分
组是刻意的：本文的主要主张是，保持承诺的修复应通
过联合面而非仅通过效用来评判。为保持双栏排版的可
读性，我们对关键的接近比较报告均值± 95% 置信区
间，使用自由度为n −1 = 49 的t 分布计算；对效用、
集合改动、插入负担和时间移动使用配对t 检验，对延
迟使用Welch t 检验，并在多重比较时应用Bonferroni
校正。
所有方法都在同一实例生成器上执行，采用匹配的
随机种子和相同的面向修复的指标集。该协议与[3] 的
任务边界一致：相同的下发前缀修复问题、相同的可见
性窗口和机动可行性结构、相同的面向修复的指标，但
不复现该论文的私有资源或绝对奖励尺度。因此，所有
报告的数值只在该协议内解释，延迟被读作相对修复代
价，奖励更新的效用不跨扰动族比较。
B. 主要结果
a) 取消: 表I报告了本文中最清晰的正面结果。
预算为2 的PALR 规则在效用上略微超过贪心全局重
优化，同时保持零任务集合改动和零被保留任务时间移
动。重要的限定是：PALR 规则应被理解为中间路线，
而非在每个轴上都是最小扰动的赢家；当单独考虑插入
负担时，最小修复仍是最保守的基线。在同一取消协议
内，PALR 达到相同的效用区间，同时把插入任务负担
从0.539 降到0.335、减少约37.8%，消除被保留任务
Greedy Minimal
PALR
0
1
2
×109
Utility
Greedy Minimal
PALR
0.00
0.02
0.04
ratio
Set Change
Greedy Minimal
PALR
0.0
0.2
0.4
ratio
Inserted Burden
Greedy Minimal
PALR
0.0
0.2
0.4
ms
Latency
Cancellation Trade-Off
图4. 取消场景在效用、集合改动、插入负担和延迟上的权衡。PALR 规则
占据效用–扰动前沿的中间区域：最小修复是零插入端点，贪心全局重优化是
激进重插入端点。
表I
取消场景（50 个实例上的均值± 95% 置信区间）。效用单位为×109。
方法
效用
集合改动
插入
移动
延迟
贪心全局重优化
2.348±0.259
0.048±0.028
0.539±0.422
24.6±12.1
0.413±0.041
最小修复
2.222±0.273
0.000
0.000
0.0
0.009±0.001
PALR 规则(B=2)
2.362±0.273
0.000
0.335±0.108
0.0
0.084±0.005
移动，并把延迟从0.413 毫秒降到0.084 毫秒、降低约
79.7%。对操作者而言，这正是低扰动修复器优于激进
后缀重建的实际有意义区间。
深入分析表明，取消结果应被读作一个权衡面而非
单一得分的胜利。最小修复是零插入端点，贪心全局重
优化是激进重插入端点，PALR 规则通过放弃部分保守
性以夺回更多效用、同时在插入量和延迟上远低于贪心
全局重优化，占据中间区间。因此PALR 与贪心全局
重优化之间的小效用差距不应被过度宣扬为大的绝对
改进，其重要性是有条件的。
b) 紧急插入: 表II和III刻画了没有冻结前缀
的紧急插入区间。核心事实是这一局限：PALR 规则在
此设置下退化为最小修复，两行在效用和扰动上数值完
全相同，微小的延迟差异可归因于实现开销。这一区间
更支持下发前缀修复的框架，而非更丰富的紧急放置主
张：三种方法都能放置紧急任务，但修复优先的方法族


## 原文件物理页 9

表II
无冻结前缀的紧急插入（均值± 95% 置信区间；FR = 0.0）。
方法
效用
集合改动
插入
移动
贪心全局重优化2.417±0.276 0.142±0.061 0.168±0.041 34.4±21.6
最小修复
2.937±0.220 0.009±0.010 0.168±0.041 11.7±10.7
PALR 规则
2.937±0.220 0.009±0.010 0.168±0.041 11.7±10.7
表III
紧急插入的延迟与严格成功率（在适用处为均值± 95% 置信区间；FR
= 0.0）。
方法
延迟(毫秒)
严格成功率
贪心全局重优化
0.406±0.044
1.00
最小修复
0.038±0.009
1.00
PALR 规则
0.039±0.013
1.00
以远小的调度移动做到这一点。当FR = 0 且紧急任务
已经能被一次最小局部编辑接纳时，当前PALR 规则
没有额外的排序信号来证明更激进的邻域扩展是合理
的，因此本文把无冻结前缀的紧急插入作为边界情形、
而非第二个头条胜利来呈现。
c) 奖励更新: 奖励更新暴露了第三种修复模
式：当前PALR 规则作为仅插入修复器，它把任务集合
扰动和被保留任务移动保持为零，只通过额外插入来恢
复效用。由于扰动本身改变了奖励尺度，表VIII和IX中
的绝对效用值只应在各自表内比较。这一区别在实践上
很重要，因为即使几何不变，奖励更新在滚动规划中也
很常见；一个能够在不触碰被保留任务的情况下充实可
编辑尾部的修复器，为操作者提供了一种在保持先前协
同工作稳定的同时响应新价值估计的方式。代价是：当
新的价值格局需要更深的结构性重排时，这样的修复器
会表现不佳，这就是本文把奖励更新视为互补而非普适
成功案例的原因。
C. 消融研究
为了量化评估插入预算这一使PALR 规则可控的
机制，我们在取消区间进行了预算扫描消融，结果汇总
在表IV中。通过逐步增大预算B，效用随预算增大而提
升，但插入量和延迟也随之增长。预算2 是最有依据的
默认值，因为它在效用上已经匹配或略微超过贪心全局
重优化，同时在插入量上远低于它、在延迟上更远低于
它。
关键设计验证表明，引入正插入预算使操作模式从
纯保持转为受控恢复，这表明插入预算与效用恢复之间
2.25
2.30
2.35
×109
Utility
Greedy ref.
0.0
0.2
0.4
0.6
ratio
Inserted Burden
0
1
2
3
4
5
Insertion Budget B
0.0
0.1
0.2
0.3
0.4
ms
Latency
Budget Frontier Under Cancellation
图5. 取消预算前沿。最有依据的工作点是B = 2：更大的预算仍能略微提
升效用，但也会因增加插入负担而侵蚀低扰动优势。
表IV
取消消融（均值± 95% 置信区间）。贪心全局重优化作为参考行纳入。
预算
效用(×109)
插入任务比例
延迟(毫秒)
贪心全局重优化(参考)
2.348±0.259
0.539±0.422
0.413±0.041
B = 0
2.222±0.273
0.000
0.012±0.001
B = 1
2.313±0.271
0.202±0.056
0.054±0.004
B = 2
2.362±0.273
0.335±0.108
0.087±0.007
B = 3
2.375±0.274
0.429±0.145
0.106±0.010
B = 5
2.388±0.276
0.585±0.229
0.130±0.018
存在显著的单调正相关关系，从而验证了我们把B 作
为可解释控制变量的设计动机的有效性。从B = 0 到
B = 2 把操作模式从纯保持改为受控恢复，而从B = 2
到B = 5 把方法推向越来越激进的后缀修改；B = 2
之后效用曲线的平坦，加上插入任务负担的持续增长，
正是本文把B = 2 视为最可信默认值而非孤立数值最
优的原因。总体来说，本消融研究证明了插入预算在
PALR 规则中不可或缺的性质：它不是一个装饰性超参


## 原文件物理页 10

表V
重冻结约束下的取消稳健性（均值± 95% 置信区间）。效用单位为×109。
设置
方法
效用
集合改动
插入
移动
FR = 0.6, 强度= 0.5
贪心全局重优化
2.413±0.270
0.056±0.028
0.597±0.417
12.5±8.3
最小修复
2.298±0.289
0.000
0.000
0.0
PALR 规则(B=2)
2.398±0.275
0.000
0.313±0.110
0.0
FR = 0.6, 强度= 1.0
贪心全局重优化
2.373±0.258
0.053±0.029
0.564±0.419
20.0±9.3
最小修复
2.256±0.277
0.000
0.000
0.021±0.042
PALR 规则(B=2)
2.364±0.268
0.000
0.342±0.106
0.021±0.042
数，而是一个花费插入容量以夺回效用、同时保持修复
局部且可审计的明确决定。
D. 稳健性评估
稳健性结果澄清了何时应该以及不应该信任
PALR。我们聚焦于最清晰地对承诺保持施压的区间：
重冻结前缀、严格有效性下的紧急插入，以及非拓扑的
奖励变化。
1) 重冻结前缀下的取消: 表V表明，在冻结比例
0.6 下，PALR 规则仍接近贪心全局重优化的效用，同
时保持零任务集合扰动和基本为零的被保留任务移动。
这是更干净的重冻结成功案例：可编辑尾部很小，但有
界修复仍能在不重开被保留工作的情况下恢复大部分
可用价值。使这一区间重要的是，可编辑尾部在扰动发
生前就已经很短，因此在不移动被保留工作的情况下恢
复效用比在基础取消设置中更难；PALR 在两种强度下
都保持在贪心全局重优化的效用带附近，支持了更窄的
主张：当扰动可被尾部级重排吸收时，有界局部修复仍
然可行。
2) 重冻结前缀下的紧急插入: 重冻结紧急区间是
最强效用导向对比方法最重要的地方。表VI和VII表明，
学习先验PUCT 对比方法在硬冻结约束下达到最高效
用，但它付出比局部修复族大得多的延迟和移动。严格
紧急成功上限对每种保持前缀的方法都是0.34，对应
50 个评估实例中的17 个。这表明一旦施加FR = 0.6，
约33 个实例在当前生成器下不可行，因此搜索优势应
在同一可行子集内解读，而不是作为更多可行实例的证
据。这正是本文想要揭示的操作升级故事：当严格成功
上限被可行性固定时，更强的搜索改变的是成功修复的
质量，而不是严格成功实例的数量。
同一张表也澄清了我们为什么不把学习先验
PUCT 行视为无条件的全局赢家：它的额外效用伴随
0
1
2
×109
Greedy
PUCT
Learned PUCT
Learned local
Operator policy
Minimal
PALR
Utility
0.0
0.1
0.2
ratio
Inserted Burden
0
5
ms
Greedy
PUCT
Learned PUCT
Learned local
Operator policy
Minimal
PALR
Latency
0.0
0.2
rate
Strict Success
Heavy-Frozen Urgent Boundary (FR=0.6)
图6. FR = 0.6 处的重冻结紧急边界。更强的搜索在相同的严格成功上限内
提升紧急效用，但付出比局部修复大得多的延迟和更大的插入任务负担。
表VI
重冻结紧急插入（均值± 95% 置信区间；FR = 0.6）。两个PUCT 行共
享相同的40 次模拟预算，PALR 规则与最小修复在当前实现中共享相同的
紧急修复决策。
方法
效用
集合改动
插入
移动
贪心全局重优化
2.374±0.220 0.041±0.027 0.085±0.049 2.4±1.6
PUCT 重优化
2.442±0.220 0.041±0.027 0.172±0.127 2.8±1.7
学习先验PUCT 2.474±0.224 0.056±0.026 0.263±0.158 9.5±3.1
学习型局部修复
2.390±0.223 0.028±0.022 0.074±0.045 0.4±0.5
算子策略修复
2.370±0.223 0.034±0.023 0.069±0.045 0.6±0.6
最小修复
2.390±0.223 0.028±0.022 0.074±0.045 1.9±1.5
PALR 规则
2.390±0.223 0.028±0.022 0.074±0.045 1.9±1.5
着明显更大的插入任务负担，以及相对于低扰动修复约
一个数量级的延迟惩罚。本文并不隐瞒更强搜索能在效
用上取胜的事实，而是把这份额外效用的代价说清楚，
并明确给出分母：在这个生成器中，所有方法都被限制
在相同的50 个中17 个严格成功。
3) 奖励更新作为非拓扑扰动: 表VIII和IX报告了
跨两个冻结比例和两个扰动强度的奖励更新网格。关键
观察是：当前PALR 规则表现为仅插入修复器，它保
持原有被保留计划不变，并通过在可编辑尾部追加或激
活新机会来获得效用；相比之下，贪心全局重优化通过
更激进地重开后缀来获得效用，这会增加移动和任务集


## 原文件物理页 11

表VII
重冻结紧急插入：延迟与严格成功率（在适用处为均值± 95% 置信区间；
FR = 0.6）。
方法
延迟(毫秒)
严格成功率
贪心全局重优化
0.184±0.013
0.34
PUCT 重优化
3.489±0.440
0.34
学习先验PUCT
9.122±1.813
0.34
学习型局部修复
0.021±0.009
0.34
算子策略修复
0.209±0.020
0.32
最小修复
0.011±0.003
0.34
PALR 规则
0.008±0.002
0.34
4
6
×109
FR=0 Utility
Greedy
Minimal
PALR
0.0
0.1
0.2
0.3
ratio
FR=0 Inserted Burden
0.25
0.50
0.75
Reward Strength
2.5
3.0
3.5
4.0
4.5
×109
FR=0.6 Utility
0.25
0.50
0.75
Reward Strength
0.00
0.05
0.10
0.15
0.20
ratio
FR=0.6 Inserted Burden
Reward-Update Behavior Across Frozen Ratios
图7. 跨冻结比例的奖励更新行为。PALR 规则表现为仅插入修复器：它保
持被保留工作，但一旦可编辑尾部变小，其效用优势就急剧收窄。
合改动。
奖励更新表最好被读作两种不同的修复模式。在
FR = 0 时，PALR 规则可以花费少量插入来收获大的
效用增益，而不移动被保留工作；在FR = 0.6 时，同
一策略被挤进一个薄得多的可编辑尾部，保持性仍然成
立，但价值恢复的空间大部分消失。因此，奖励更新比
其他扰动更清晰地把“稳定几何下的价值收获”与“深
度重排”区分开来。
E. 兼容性研究
为了证明PALR 规则与其他技术路线的正交性及
兼容潜力，我们将其与外部的推理期PUCT 搜索和学
习先验结合到相同的冻结感知修复框架下。实验表明，
表VIII
无冻结前缀的奖励更新（均值± 95% 置信区间；FR = 0.0）。效用单位为
×109，仅在此扰动族内可比。
强度
方法
效用
集合
增加
移动
0.2
贪心全局重优化
2.755±0.308
0.132±0.049
0.149±0.041
36.5±15.8
0.2
最小修复
2.552±0.298
0.000
0.000
0.0
0.2
PALR 规则
3.818±0.321
0.000
0.323±0.053
0.0
0.8
贪心全局重优化
5.779±0.784
0.239±0.052
0.281±0.071
61.8±17.5
0.8
最小修复
4.422±0.701
0.000
0.000
0.0
0.8
PALR 规则
7.301±0.767
0.000
0.323±0.053
0.0
表IX
重冻结前缀下的奖励更新（均值± 95% 置信区间；FR = 0.6）。效用单位
为×109，仅在此扰动族内可比。
强度
方法
效用
集合
增加
移动
0.2
贪心全局重优化2.583±0.298 0.041±0.032 0.057±0.031
2.2±1.6
0.2
最小修复
2.552±0.298
0.000
0.000
0.0
0.2
PALR 规则
2.652±0.297
0.000 0.200±0.064
0.0
0.8
贪心全局重优化4.664±0.754 0.076±0.037 0.138±0.064 10.2±4.5
0.8
最小修复
4.422±0.701
0.000
0.000
0.0
0.8
PALR 规则
4.613±0.712
0.000 0.200±0.064
0.0
在重冻结紧急区间，结合后的学习先验PUCT 方案在
保持相同0.34 严格成功上限的前提下把紧急效用进一
步提升至2.474（相对贪心全局重优化的2.374 提升约
4.2%）。这一结果表明PALR 的修复契约具备良好的可
组合性，能够有效吸纳外部搜索与学习增强信息，突出
了本文方法在“默认快速局部修复、必要时升级到更强
搜索”这一分层调度场景方面的强大适应性与有效性。
延迟证据同样支持这一分层视角：PALR 在整个被接受
的协议中保持亚毫秒级，贪心全局重优化慢几倍，学习
先验PUCT 重规划器在最难的重冻结紧急设置下约慢
两个数量级（9.122 毫秒对0.008 毫秒），因此有界局部
修复足够便宜，可以在固定的对地观测卫星契约下充当
默认快速路径。
VI. 结论
我们把动态对地观测调度刻画为对部分已发布计
划的修复，并把PALR 作为一种有界局部响应加以评
估。结果在取消之后最清晰地支持PALR：它匹配贪心
全局重优化的效用带，同时引入的扰动远小于后者。奖
励变化展示了第二种情形，其中不变的几何让PALR
能通过小规模尾部插入获得价值，而不重开保留工作。
它的界限也是明确的：没有冻结前缀时紧急插入退化为
最小修复；当FR = 0.6 时，更强的搜索只在同一50


## 原文件物理页 12

中17 的严格成功上限内提高价值，且延迟与移动更大。
因此，PALR 不是更重搜索的通用替代品，而是一种可
信的快速首次响应，其升级条件可通过实验识别。
参考文献
[1] B. Ferrari, J.-F. Cordeau, M. Delorme, M. Iori, and R. Orosei,
“Satellite
scheduling
problems:
A
survey
of
applications
in
earth and outer space observation,” Computers & Operations
Research, vol. 173, p. 106875, 2025. [Online]. Available: https:
//doi.org/10.1016/j.cor.2024.106875
[2] S. Krigman, T. Grinshpoun, and L. Dery, “Scheduling of earth
observing
satellites
using
distributed
constraint
optimization,”
Journal
of
Scheduling,
vol.
27,
pp.
507–524,
2024.
[Online].
Available: https://doi.org/10.1007/s10951-024-00816-x
[3] A. Jacquet, G. Infantes, E. Benazera, V. Baudoui, J. Guerra,
and S. Roussel, “Earth observation satellite scheduling with graph
neural networks and monte carlo tree search,” 2024. [Online].
Available: https://arxiv.org/abs/2408.15041
[4] J. Qi, M. Hu, L. Xing, and Z. Su, “Deep reinforcement learning-
assisted large neighborhood search for online scheduling large-scale
emergency tasks to earth-observing satellites,” Expert Systems
with Applications, vol. 291, p. 128502, 2025. [Online]. Available:
https://doi.org/10.1016/j.eswa.2025.128502
[5] X. Feng, Y. Li, and M. Xu, “Multi-satellite cooperative scheduling
method
for
large-scale
tasks
based
on
hybrid
graph
neural
network
and
metaheuristic
algorithm,”
Advanced
Engineering
Informatics, vol. 60, p. 102362, 2024. [Online]. Available: https:
//doi.org/10.1016/j.aei.2024.102362
[6] M.
Caleiras,
S.
Moniz,
and
P.
Nascimento,
“A
constraint
programming
model
for
the
super-agile
earth
observation
satellite
imaging
scheduling
problem,”
in
Proceedings
of
the
15th
International
Conference
on
Operations
Research
and
Enterprise
Systems,
2026,
pp.
110–121.
[Online].
Available:
https://doi.org/10.5220/0014407000004055
[7] P. Li, H. Wang, Y. Zhang, and R. Pan, “Mission planning for
distributed multiple agile earth observing satellites by attention-
based deep reinforcement learning method,” Advances in Space
Research, vol. 74, no. 5, pp. 2388–2404, 2024. [Online]. Available:
https://doi.org/10.1016/j.asr.2024.06.003
[8] P. Li, P. Cui, and H. Wang, “Mission sequence model and deep
reinforcement learning-based replanning method for multi-satellite
observation,” Sensors, vol. 25, no. 6, p. 1707, 2025. [Online].
Available: https://doi.org/10.3390/s25061707
[9] H. Li, Y. Li, Q. Q. Meng, X. Li, L. Shao, and S. Zhao, “An
onboard periodic rescheduling algorithm for satellite observation
scheduling problem with common dynamic tasks,” Advances in
Space Research, vol. 73, no. 11, pp. 5242–5253, 2024. [Online].
Available: https://doi.org/10.1016/j.asr.2024.02.038
[10] Y.
Long,
C.
Shan,
W.
Shang,
J.
Li,
and
Y.
Wang,
“Deep reinforcement learning-based approach with varying-scale
generalization
for
the
earth
observation
satellite
scheduling
problem
considering
resource
consumptions
and
supplements,”
IEEE
Transactions
on
Aerospace
and
Electronic
Systems,
vol.
60,
no.
3,
pp.
2572–2585,
2024.
[Online].
Available:
https://doi.org/10.1109/TAES.2024.3379169
[11] J.
Chen,
F.
Wang,
Y.
Chen,
L.
He,
Y.
Du,
J.
Wu,
and
Y. Chen, “A generalized bilevel optimization model for large-scale
task scheduling in multiple agile earth observation satellites,”
Knowledge-Based Systems, vol. 309, p. 112809, 2025. [Online].
Available: https://doi.org/10.1016/j.knosys.2024.112809
[12] S.
Holguin
Jimenez,
W.
Trabelsi,
and
C.
Sauvey,
“Multi-
objective production rescheduling: A systematic literature review,”
Mathematics, vol. 12, no. 20, p. 3176, 2024. [Online]. Available:
https://doi.org/10.3390/math12203176
[13] C. Zhang, M. Juraschek, and C. Herrmann, “Deep reinforcement
learning-based dynamic scheduling for resilient and sustainable
manufacturing: A systematic review,” Journal of Manufacturing
Systems, vol. 77, pp. 962–989, 2024. [Online]. Available: https:
//doi.org/10.1016/j.jmsy.2024.10.026
[14] N. Ouahabi, A. Chebak, O. Kamach, O. Laayati, and M. Zegrari,
“Leveraging digital twin into dynamic production scheduling: A
review,” Robotics and Computer-Integrated Manufacturing, vol. 89,
p. 102778, 2024. [Online]. Available: https://doi.org/10.1016/j.rcim.
2024.102778
[15] S. Lendl, U. Pferschy, and E. Rener, “Rescheduling with new orders
under bounded disruption,” INFORMS Journal on Computing,
vol. 36, no. 6, pp. 1654–1675, 2024. [Online]. Available: https:
//doi.org/10.1287/ijoc.2023.0038
[16] R. Chen, T. C. E. Cheng, C. T. Ng, J.-Q. Wang, H. Wei, and
J. Yuan, “Rescheduling to trade off between global disruption
of
original
jobs
with
flexibility
and
scheduling
cost
of
new
jobs,”
Omega,
vol. 128,
p.
103114,
2024.
[Online].
Available:
https://doi.org/10.1016/j.omega.2024.103114
[17] Y. Bengio, A. Lodi, and A. Prouvost, “Machine learning for
combinatorial optimization: A methodological tour d’horizon,”
European Journal of Operational Research, vol. 290, no. 2, pp.
405–421, 2021. [Online]. Available: https://doi.org/10.1016/j.ejor.
2020.07.063
[18] N. Sonnerat, P. Wang, I. Ktena, S. Bartunov, and V. Nair, “Learning
a large neighborhood search algorithm for mixed integer programs,”
2021. [Online]. Available: https://arxiv.org/abs/2107.10201
[19] Y.
Wu,
W.
Song,
Z.
Cao,
and
J.
Zhang,
“Learning
large
neighborhood
search
policy
for
integer
programming,”
2021.
[Online]. Available: https://arxiv.org/abs/2111.03466
[20] A. Hottung and K. Tierney, “Neural large neighborhood search for
routing problems,” Artificial Intelligence, vol. 313, p. 103786, 2022.
[Online]. Available: https://doi.org/10.1016/j.artint.2022.103786
[21] R. Reijnen, Y. Zhang, H. C. Lau, and Z. Bukhsh, “Online control
of adaptive large neighborhood search using deep reinforcement
learning,” 2022. [Online]. Available: https://arxiv.org/abs/2211.
00759
[22] G.
Hendel,
“Adaptive
large
neighborhood
search
for
mixed
integer programming,” Mathematical Programming Computation,
vol. 14, no. 2, pp. 185–221, 2022. [Online]. Available: https:
//doi.org/10.1007/s12532-021-00209-7
[23] J. Zhou, Y. Wu, Z. Cao, W. Song, J. Zhang, and Z. Chen,
“Learning large neighborhood search for vehicle routing in airport
ground handling,” 2023. [Online]. Available: https://arxiv.org/abs/
2302.13797


## 原文件物理页 13

[24] T. M. Mazzoli, L. Kletzander, P. Van Hentenryck, and N. Musliu,
“Investigating large neighbourhood search for bus driver scheduling,”
in Proceedings of the 34th International Conference on Automated
Planning and Scheduling (ICAPS), 2024, pp. 360–368. [Online].
Available: https://doi.org/10.1609/icaps.v34i1.31495
[25] J. Cai, T. Huang, and B. Dilkina, “Learning backdoors for mixed
integer linear programs with contrastive learning,” in ECAI 2024,
2024. [Online]. Available: https://doi.org/10.3233/faia240768
[26] W. Chen, S. Koenig, and B. Dilkina, “Marl-lns: Cooperative
multi-agent reinforcement learning via large neighborhoods search,”
2024. [Online]. Available: https://arxiv.org/abs/2404.03101
[27] C. Gao, H. Shang, K. Xue, D. Li, and C. Qian, “Towards
generalizable
neural
solvers
for
vehicle
routing
problems
via
ensemble
with
transferrable
local
policy,”
in
Proceedings
of
the
Thirty-Third
International
Joint
Conference
on
Artificial
Intelligence (IJCAI), 2024, pp. 6914–6922. [Online]. Available:
https://doi.org/10.24963/ijcai.2024/764
[28] A. I. Garmendia, Q. Cappart, J. Ceberio, and A. Mendiburu,
“MARCO:
A
memory-augmented
reinforcement
framework
for
combinatorial optimization,” in Proceedings of the Thirty-Third
International Joint Conference on Artificial Intelligence (IJCAI),
2024, pp. 6931–6939. [Online]. Available: https://doi.org/10.24963/
ijcai.2024/766
[29] Z. Lin, Y. Wu, B. Zhou, Z. Cao, W. Song, Y. Zhang, and
S. Jayavelu, “Cross-problem learning for solving vehicle routing
problems,” in Proceedings of the Thirty-Third International Joint
Conference on Artificial Intelligence (IJCAI), 2024, pp. 6958–6966.
[Online]. Available: https://doi.org/10.24963/ijcai.2024/769
[30] T. Wu, H. Cui, T. Guan, Y. Wang, and Y. Jin, “ReinforceNS:
Reinforcement
learning-based
multi-start
neighborhood
search
for
solving
the
traveling
thief
problem,”
in
Proceedings
of
the
Thirty-Third
International
Joint
Conference
on
Artificial
Intelligence (IJCAI), 2024, pp. 7038–7046. [Online]. Available:
https://doi.org/10.24963/ijcai.2024/778
[31] J. Zhang, C. Luo, Z. Su, Q. Zhang, Z. Lu, J. Ding, and Y. Jin, “NS4S:
Neighborhood search for scheduling problems via large language
models,” in Proceedings of the Thirty-Fourth International Joint
Conference on Artificial Intelligence (IJCAI), 2025, pp. 8687–8695.
[Online]. Available: https://doi.org/10.24963/ijcai.2025/966
[32] H. Ye, J. Wang, H. Liang, Z. Cao, Y. Li, and F. Li, “GLOP: Learning
global partition and local construction for solving large-scale routing
problems in real-time,” in Proceedings of the AAAI Conference
on Artificial Intelligence, vol. 38, no. 18, 2024, pp. 20 284–20 292.
[Online]. Available: https://doi.org/10.1609/aaai.v38i18.30009
[33] Z.
Sun
and
Y.
Yang,
“DIFUSCO:
Graph-based
diffusion
solvers for combinatorial optimization,” in Advances in Neural
Information
Processing
Systems
36,
2023.
[Online].
Avail-
able: https://proceedings.neurips.cc/paper_files/paper/2023/hash/
0ba520d93c3df592c83a611961314c98-Abstract-Conference.html
[34] S. Attieh, N. Dang, C. Jefferson, I. Miguel, and P. Nightingale,
“Athanor: Local search over abstract constraint specifications,”
Artificial Intelligence, vol. 340, p. 104277, 2025. [Online]. Available:
https://doi.org/10.1016/j.artint.2024.104277
[35] Z. Liu, W. Xiong, C. Han, and X. Yu, “Deep reinforcement learning
with local attention for single agile optical satellite scheduling
problem,” Sensors, vol. 24, no. 19, p. 6396, 2024. [Online]. Available:
https://doi.org/10.3390/s24196396
[36] Q. Cappart, D. Chételat, E. B. Khalil, A. Lodi, C. Morris,
and P. Velickovic, “Combinatorial optimization and reasoning
with
graph
neural
networks,”
Journal
of
Machine
Learning
Research, vol. 24, no. 130, pp. 1–61, 2023. [Online]. Available:
https://jmlr.org/papers/v24/22-0459.html
[37] S. Brody, U. Alon, and E. Yahav, “How attentive are graph
attention networks?” 2021. [Online]. Available: https://arxiv.org/
abs/2105.14491
[38] T. Cazenave, “Batch monte carlo tree search,” 2021. [Online].
Available: https://arxiv.org/abs/2104.04278
[39] X. Wang, F. Zhao, Z. Shi, and Z. Jin, “Deep reinforcement
learning-based
periodic
earth
observation
scheduling
for
agile
satellite constellation,” Journal of Aerospace Information Systems,
vol. 20, no. 8, pp. 508–519, 2023. [Online]. Available: https:
//doi.org/10.2514/1.I011209
