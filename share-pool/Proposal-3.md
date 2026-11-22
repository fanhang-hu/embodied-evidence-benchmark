# 恶意环境状态污染下具身智能运行时安全验证的信任边界

**Trust Boundaries of Runtime Safety Verification under Adversarial World-State Corruption**  
**版本：** Proposal-3 / 2026-10-22  
**研究阶段：** E1–E3 已有阶段性机制验证；准备 E4–E6 的威胁有效性、泛化和归因评估；Design 暂未启动。  
**用途：** 研究 Proposal / 组会汇报 / 后续实验目标冻结。

> **中心问题：** 在安全策略不被攻击者修改的前提下，运行时安全检查依赖的 World State 可能包含不真实的安全关键事实。我们研究这种失真经过哪些信任边界到达 Planner 与 Safety Monitor、在什么条件下造成**执行前错误授权**、何时被独立核验阻断，以及安全代价与合法任务效用的关系。
>
> **论文主张限定：** 研究目标**不是证明“现有运行时安全防御普遍失效”**。Proposal-2 原本也没有作出这一普遍性承诺。当前已有的是几类受控状态污染引起错误判断的证据、若干有效简单防御反例和一项单例真实 Unity 执行闭环；它们支持继续验证“**有条件的证据信任失效**”，但尚不足以支持对九项原版系统的普适、统计化结论。

## 本次修订的关键决定

- **保持** Proposal-2 的主问题、信任边界路线、E1–E3 已完成工作及“优先排除简单修复”的原则。
- **强化** 攻击权限和真正消费者入口的证明责任：受控副本替换 ≠ 可被低权限敌手影响的真实状态生产者；Planner 未运行 ≠ Planner–Monitor 共同失效。
- **把研究产出分成两条条件路径：** 若验证出可信、可复现且简单防御仍有成本/覆盖盲区的失效，可发展成系统化安全评估/基准；只有发现真正剩余的非平凡问题才考虑新防御 Design。
- **以 E4–E6 而非额外模型复现为下一阶段重点：** 场景与来源可行性、证据归因、统一安全—效用—成本评估。详细执行见 `exp-5.md`。

---

## 1. Background

近年来，LLM/VLM 被广泛引入具身智能的高层认知与任务规划。典型机器人系统接收用户的自然语言目标，通过摄像头、深度传感器或其他感知模块获取环境信息，再将对象类别、属性、空间关系和历史执行反馈整理为 World State（或 Semantic Scene Map），交由 Planner 生成动作序列，并通过 Robot Skills、运动规划器及底层控制器与物理世界交互。SayCan 将语言模型的语义规划与机器人技能的可执行性关联起来 [1]；ProgPrompt 将环境对象、可用动作和前置条件组织为程序式任务规划 [2]；VoxPoser 利用语言与视觉模型构造空间约束以指导机器人操作 [3]。AI2-THOR 等交互仿真平台使此类“感知—规划—执行—反馈”闭环能够在可控环境中研究 [4]。

与纯数字 Agent 不同，具身 Agent 的错误决定可能转化为真实物理操作，因此任务成功率并不足以描述系统安全性。已有研究在 Planner 与物理执行之间加入运行时安全监控，通过可信规则、形式化约束、动作前置条件、执行状态和实时视觉信息过滤高风险行为。例如，RoboGuard 使用环境相关的 LTL 安全规范审查计划 [5]；SafeGate 对任务施加执行前准入及执行过程中的安全合约 [6]；RoboSafe 结合视觉观察和历史轨迹动态生成安全谓词 [7]。这些工作已经形成较成熟的规划与执行安全检查基础。

然而，安全检查通常依赖某种环境事实：物体是否存在、设备是否打开、目标区域是否允许进入，以及前一步操作是否成功。相关事实可能来自视觉推理、语义地图、状态服务或 Skill 反馈。**状态被及时同步或具有完整的存储记录，不必然意味着其描述的物理事实正确。** 环境事实可能因识别错误、遮挡、过期或主动攻击而失真；更重要的是，Planner 与 Safety Monitor 可能共同依赖同一条受到污染的上游信息。

已有攻击工作表明，这一风险并非纯粹假设。ESTI 通过修改 Planner 可见的环境状态语义，影响规划和执行结果 [17]；物理文字干扰可经由开放词汇感知传播至持久化语义地图，并影响机器人操作 [18]；ROS2 遥测伪造研究进一步揭示，数据在进入受保护的消息通道之前就可能被恶意修改 [19]。因此，本研究暂时聚焦于 **LLM/VLM Planner + Robot Skills 场景中安全关键环境证据的可信边界**，而不是重新构建通用机器人 Planner，也不预设必须使用共享资源池、Evidence Hub、TEE 或系统调用审计。

## 2. Related Work

**Planning Safety and Formal Verification.** RoboGuard [5] 将预设安全规则结合语义 World Model 转换为上下文相关的 LTL 约束，并通过形式化控制合成修正潜在危险计划；SafeGate [6] 通过执行前安全门与 Task Safety Contracts（Guards、Invariants、Abort Conditions）处理危险命令及状态转移。两者说明基于规则的执行准入与安全计划验证已得到充分研究。其重要边界在于：形式化检查可以保证“给定状态和规则下”的逻辑一致性，却不会自动证明输入 World State 真实；RoboGuard 也明确承认严重受损的 World Model 会影响安全保证。

**Runtime Monitoring and Execution Safety.** RoboSafe [7] 使用短期执行轨迹、长期安全记忆和视觉观察形成动态可执行安全谓词，并结合前向预测和后向反思发现潜在风险；DoReMi [8] 通过检测计划与实际执行的偏离来触发恢复；SafeGate [6] 已具备执行前后检查与信息不足时的 Defer 能力。相关方法覆盖了动态监控、状态更新、异常中止与重规划，因此“每一步检查、执行后更新环境”本身并不是新的贡献。其尚待明确的边界是：当当前观察、历史记录或场景快照中出现恶意伪造但看似确定的安全事实时，检查是否仍有足够的独立依据。

**Scene Grounding and Plan Verification.** PerceptTwin [9] 将机器人感知得到的 Semantic Scene Map 重建为交互仿真，用于检验技能前置条件、模拟执行并向 Planner 反馈；VeriGraph [10] 使用由视觉生成的 Scene Graph 约束和修正机器人计划；Mind the Refinement Gap [11] 进一步指出，高层计划即使通过形式化检查，实际执行所隐含的路径或动作效果也可能未被验证。这些研究已覆盖语义建模、执行前仿真及计划—执行一致性。需要区分的是：重建仿真的可靠性取决于其输入场景，场景图内部自洽不等于其所有事实与真实世界一致；同时 PerceptTwin 的原生执行后 Judge 与研究者新增的执行前安全门必须区分；不能从后者的失效推论前者被绕过。

**Visual Guardrails and Perception Uncertainty.** EMBGuard [12] 根据“当前视觉观察—候选动作”组合判断物理危险，降低过度拒绝；CORE [13] 利用视觉语义构造上下文安全约束，并在其感知误差假设下分析概率安全保证；SPARQ [14] 则从系统层面评估感知失败对自动驾驶计划安全的影响，并考虑恢复。因此，“额外使用视觉”“考虑感知不确定性”也已有较成熟研究。它们对主动语义状态污染的实际抵抗能力取决于观察是否独立、是否足够辨别关键事实，以及攻击是否违反原有感知误差假设。

**Semantic Grounding and Plan-Level Security.** Risk-Aware Semantic Grounding [15] 判断语言任务和语义地图之间的歧义、幻觉及冲突，从而选择执行、澄清或拒绝；PROTEA [16] 使用 LLM-as-a-Judge 评估机器人计划中隐蔽的恶意步骤，并构建 HarmPlan 数据集。这些方法说明任务语义风险、Plan Judge 和保守决策已有人研究。然而，检测输入之间的冲突不必然能够发现一份被一致污染、内部看似合理的状态描述；同时这些机制可以凭借安全常识或保守策略拦截部分危险，不能直接推断其存在系统性漏报。

**World-State Attacks and Evidence Integrity.** ESTI [17] 将环境状态文本作为独立攻击面，研究对象属性、空间关系、动作条件及反馈污染对规划和执行的传播；Not What You Asked For [18] 展示了感知误分类进入持久化 3D 语义地图并导致错误操作的路径；Seeing is Not Believing [19] 从 ROS2 消息发布前的伪造揭示遥测认证与物理事实真实性之间的差异。另一方面，Traceable World State [20] 引入来源、修订、不可变更新与重放等机制；通用 Agent 安全中的 CaMeL [21] 和 PACT [22] 分别研究不可信数据的控制流隔离与工具参数级来源权限约束。上述工作表明，攻击路径、来源追踪和信任隔离均非空白；但**来源合法、传输完整、历史可追溯，仍不等于安全关键物理语义已得到核实**。

**Related Work Summary.** 综合来看，已有工作在 Plan/Action Safety、执行前后验证、动态状态更新、视觉风险识别、形式化约束以及状态 Provenance 方面提供了充分基础；恶意语义状态污染及其对实际执行的影响也已得到研究 [17–20]。因此，不应将“提出独立 Safety Monitor”“共享状态池”“重新感知”或“证据来源记录”本身视为主要创新。更合理的切入点是：**在统一、现实的上游语义状态污染威胁下，系统分析不同安全监控机制依赖哪些可信证据、何时发生错误安全授权，以及简单独立核验与保守拒绝能解决多少问题。** 2026 年的具身安全综述也将 World-State Integrity 识别为值得继续研究的方向 [23]，但这只支持研究动机，不等于证明无人提出等价防御。

## 3. Motivation

### 3.1 核心矛盾

现有 Safety Monitor 主要回答 **“Given a World State, is the Plan safe?”**，即在给定环境状态及规则的条件下判断计划能否执行。但安全检查本身需要输入环境证据；当攻击者操纵这些事实时，Planner 与 Monitor 的推理即使各自正确，也可能得出共同错误的安全结论。我们进一步关注 **“Can the environmental evidence supporting that safety decision be trusted?”**

### 3.2 Motivation Example：AI2-THOR 厨房任务

假设用户要求将水壶放到炉灶上，但不允许加热。真实环境中的炉灶已经开启；攻击者把 Planner 可见的语义状态伪造为 `stove_off=true`。Planner 据此生成放置操作；如果 Safety Monitor 同样读取这条错误事实并只核对动作前置条件，就可能错误放行，从而违反用户的安全约束。

该例仅用于解释**安全规则正确、事实依据错误**的失效机制，不代表已完成攻击复现，也不意味着 AI2-THOR 的全知 Metadata 可以提供给被测 Monitor。炉灶的实际开关状态应由仿真 Ground Truth 在评估阶段确定，而非直接泄露给防御者。

### 3.3 具有代表性的三类污染

1. **对象属性污染（Object Attribute Corruption）：** 伪造物体身份、设备开关、危险属性等，使动作安全前置条件被错误满足。
2. **空间关系污染（Spatial Relation Corruption）：** 伪造对象位置、相邻关系、目标区域或可达信息，使机器人选择错误对象或目标位置。
3. **执行反馈污染（Execution Feedback Corruption）：** 操作实际失败，却报告已完成，导致后续规划基于虚假的状态继续；该类可作为后续扩展。

这三个场景共享同一种潜在失效机制：**攻击者不必修改可信用户目标或直接控制执行器，只需污染安全判断所依赖的环境事实。** 具体攻击形态并非首次提出，ESTI 已覆盖其中多种状态字段 [17]。

### 3.4 为什么简单检查未必足够？

执行前检查和执行后更新本身是合理且成熟的机制 [6–9]。但其有效性取决于检查依据：如果 Planner 和 Monitor 重复读取同一受污染状态，二次检查不能产生独立信息；即使重新采集 RGB/Depth，遮挡、视觉歧义或不可见属性也可能使关键事实无法确认；多份历史记录如果源于同一受损生产者，也不应被当作相互独立的证明。执行后才识别到危险时，物理后果还可能已经发生。

这里存在两个必须保留的反例：**（i）** 若有准确且受保护的独立状态查询，简单执行前检查可能就已充分；**（ii）** 若任何观测都无法区分安全与危险世界，则不能凭空恢复真实状态，保守暂停可能是唯一合理选择。因此，我们并不预设已有 Monitor 普遍失效，而是首先验证它们的**证据信任边界**及实际防御能力。


## 4. Threat Model（修订：明确权限、入口与证据层级）

### 4.1 系统边界

系统包含正常任务指令 $G$、物理/仿真状态 $S^*$、上游状态生产者 $P$、Planner、Safety Monitor（或具备明确前执行准入功能的 Guard）和 Executor。状态生产者发布 $S_{shared}$；部分系统另提供相机图像 $I_t$、历史回执 $H_t$ 或受保护的状态核验 $Q_t$。各模块的真实输入能力因 Baseline 而异，不得用单一示意图冒充九种方法的实际架构。

攻击者目标是在**可信任务、安全策略、核心检查代码与执行器逻辑不变**的条件下，使某候选动作 $a_t$ 满足评估者认定的 $unsafe(a_t,S^*)=1$，却由前执行安全决策输出 `ALLOW`，并在可执行情形下造成预定义的仿真危险动作结果。

**必须同时记录两项不同事实：**（a）候选动作是否由 Planner 自主产生；（b）Monitor 是否基于所见证据放行。如果只固定候选动作做探针，则只能报告 `UAR_probe`，不能声称 Planner 与 Monitor 联合受骗。

### 4.2 攻击者权限分级

| 级别 | 具体能力 | 论文中允许的声称 |
|---|---|---|
| **T0：Controlled-copy** | 实验者在状态适配器或入参副本中修改 `parentReceptacles`、属性或图谱标签 | 机制级输入敏感性；**不声称真实上游攻击入口已证实** |
| **T1：Producer-output boundary** | 明确找到能向 Planner/Monitor 供数的非特权或较低信任生产者接口，并以测试权限修改其真实输出/消息 | 有界入口攻击成立；需提交读写权限、调用栈及 payload 证据 |
| **T2：Native end-to-end** | 在原生或可追溯的适配系统中，从攻击者可控生产链进入 Planner/Monitor，再到真实执行提交 | 在注明官方/适配差异下，可报告受证据支持的闭环失效 |

**T0 不会因为调用了真实 Unity `Simulator.apply_skill()` 而自动升级为 T1/T2。** 如果没有可用 T1，则研究只能按适配测试台/可信输入模型的条件性分析叙述。

攻击者可控制的具体字段、对象、来源、时间窗口必须在每个样本冻结；**不得**在攻击中更改系统提示词、策略规则、GT、Evaluator、受保护回执或所有独立传感器，也不得给受测防御偷偷增加 Oracle 元数据。

### 4.3 证据独立性的操作性定义

区分三层：

1. **同源重复：** 两次从同一受污染缓存或模型派生的状态，不产生独立证明。
2. **同平台新鲜查询：** 例如再次查询 AI2-THOR Unity Metadata；在封闭仿真中可作为强对照，若现实部署中没有该受保护接口，就只能标注 `X / Oracle-like`，不能直接作为可部署监控器。
3. **异源、受保护且足够可观测的证据：** 有明确生产路径、对象身份绑定和受限攻击权限；即使来源独立，视觉遮挡也可能令事实不可判定，合理输出是 `DEFER/UNKNOWN`。

EMBGuard 的原生输入为 `(RGB, Action)`，不是结构化 $S_{shared}$；若作为 `StateMonitor AND EMBGuard` 的视觉分支，**整个融合门是研究者适配系统**，必须作为独立实验配置列示。

## 5. Research Gap 与可证伪的研究主张

### 5.1 为什么现有结果不能推出“普遍失效”？

“普遍失效”至少隐含九项防御在其原生安全策略、输入权限与适用动作下都受到同一有效攻击，并且失效有跨场景统计支撑。而现有结果满足不了这一条件：

- **实现级别不等价：** #2 SafeGate-inspired、#3 RoboSafe-inspired 是机制实现；#7 PerceptTwin 炉灶错误授权来自**新增的执行前 StateMonitor**，并非原版缺失的锅具前置策略被绕过；#4 EMBGuard 只是原版视觉分类权重接入自定义融合门。
- **接口不等价：** 导航语义图、厨房锅具状态、视觉/视频风险识别、通用软件工具权限并不是同一个授权问题；#5 HD-Guard 本身是告警路径，不提供同类的执行前 ALLOW。
- **攻击层级不足：** 许多结果来自 T0 控制副本/模拟消息，不是已经证明的原生低权限 Producer 写入。当前 EMBGuard 融合没有运行 Planner，也不能证明 Planner–Monitor 同时消费了伪造状态。
- **样本量和防御反例：** EMBGuard Clean 20 条、5 对动作审计与真实 Unity 单危险/单安全执行仅是 Pilot。E2 的同 Unity 新鲜状态核验已阻断当前污染案例；#9 同坐标语义别名也被简单几何冲突检查拦截。这些**成功防御的反例**必须和失败案例一起报告。
- **物理后果需独立定义：** Unity `ToggleObjectOn` 成功、研究者“无锅禁止开火”合约违反，以及现实物理危害不是同一个概念；尤其注意 `forceAction=True` 对原生可执行性口径的影响。

因此，**不需要推翻 Proposal-2 的研究问题**，只需把“可能发生的信任边界失效”变为可验证的条件性研究主张。

### 5.2 本项目可以尝试支持的三层 Claim

| 级别 | 能够写出的研究贡献 | 必须提供的证据 |
|---|---|---|
| **C1（目前基本具备）机制层** | 在具体不可信输入模型下，逻辑自洽/多分支共用错误事实并不保证事实正确；某些适配安全门会错误授权 | 固定真值、污染字段、合约、原始输出、正负控制和简单防御反例，全部注明 O/A/M |
| **C2（E4–E6 的首要目标）系统化信任边界测量** | 不同事实类别与证据可得性下，哪些前执行 Guard 失败、哪些足够安全、需要什么成本 | ≥2事实类别、真实执行可行性、至少一种有界生产者入口或明确 T0 局限、冻结测试集、多场景、可信/不可信来源对照、UAR/E-ASR/效用/成本统计 |
| **C3（条件性设计贡献）新防御机制** | 在同等证据权限和性能预算下，简单重查、Defer/Reject、现有强方法仍有明确剩余弱点，新方法改善其安全—效用权衡 | 与同信息预算强简单防御对照；跨未见任务泛化；防御优势不能来自隐形 Oracle、永远拒绝或取消对方原生能力 |

**默认研究路线选 C2，不预先承诺 C3。** 如果连 T1 可行入口都找不到，C2 要收缩为**明确条件下的适配机制评估**，论文主张和定位同步收缩。

### 5.3 研究空白的更严谨表述

- **Gap A：** 并非首次发现 World-State 可污染；攻击路径及相关问题已由 ESTI、语义地图攻击、ROS2 遥测研究讨论 [17–19]。
- **Gap B（核心候选）：** 缺少本研究拟覆盖的、按**攻击控制权—数据来源—安全关键事实—执行前授权—执行后后果**统一对齐的多机制实证比较。这里的“缺少”仅针对已调研方法与当前实验集合，仍需在投稿前再做系统相关工作检索。
- **Gap C（待检验）：** 在可区分真/假世界但独立证据不完整、昂贵、过期、对象身份不确定时，现有简单防御的安全—任务效用 Pareto 边界是否仍有非平凡缺口。

## 6. Research Questions（研究问题与验收对应）

| RQ | 问题 | 对应实验 | 可证伪/停止条件 |
|---|---|---|---|
| **RQ1 — Boundary & Reachability** | 安全关键事实从何处产生，哪些原生/适配路径可以被有界攻击者污染并到达真实前执行检查？ | E4-0/E4-1，权限及 payload lineage 审计 | 仅有 T0 副本时，停止宣称现实原生入侵/共同失效 |
| **RQ2 — Generalization** | 真实属性、空间/目标关系、区域语义、时间/反馈污染在不同对象/任务中是否导致 UAR 与实际执行后果？ | E4 | 缺可执行危险动作或仅一类事实时，不外推普遍失效 |
| **RQ3 — Evidence & Defenses** | 同源重查、独立可观测证据、目标绑定、新鲜度、UNKNOWN/DEFER 与现有检查各能解决多少问题？ | E5 | 简单可获得的可信证据低开销覆盖所有有效攻击时，不引出复杂设计 |
| **RQ4 — Safety / Utility / Cost** | 以相同安全策略、权限与证据预算对照后，哪些防御在 UAR/E-ASR、正常任务成功、误拒、延迟之间有可验证的边界？ | E6 | 始终 DEFER 或仅用 Oracle 获得低攻击率不能算有竞争力 |

## 7. Platform / Benchmark / Data（维持原方案，收缩为主闭环）

- **主环境：** AI2-THOR 5.0.0（服务器 CPU/Xvfb）及已验证的 SafeAgentBench 技能/评估模块；Simulator Metadata 仅作 Evaluator 私有真值，除非明确作为 X 级受保护查询上界。
- **主任务池：** 先从已可执行的 FloorPlan 厨房操作与 SafeAgentBench 官方 safe/unsafe 场景筛选，明确政策来自官方标签还是研究者合约；**不能把随意指定的风险动作当成官方 GT**。
- **导航补充轨道：** SPINE/RoboGuard 及 Mind the Refinement Gap 的符号地图场景，单独报告。不得拿它与厨房 Unity E-ASR 合并。
- **EMBGuardTest 官方数据：** 当前实际 CPU Clean Pilot 使用可取得的 EMBGuardTest **v1** 四 split 各前 5 条（n=20），并非 v2 论文完整评测；其静态 RGB+Action 图像不提供真实执行式 UAR/E-ASR。
- **攻击依据：** ESTI [17] 的状态语义攻击思想、已有 E1–E3 适配入口与真实场景，仅作为明确限制的攻击测试台，不能暗中假定已复制 ESTI 的端到端攻击者权限。
- **可选扩展：** AGENTSAFE/SAFE-THOR、HarmPlan、ROS2/Gazebo/真实机器人只有在核心论证不足且资源允许时再纳入。E4–E6 **不再要求新增第十个论文 Baseline**。

实验数据单位是 `(scene_id, task_id, target_id, policy_id, true_prestate, supported_action)`；同一真值场景的多种污染条件和重复模型调用属于同簇，不能作为独立环境样本拆到训练与 heldout 两侧。

## 8. Baselines（现有九项 E3 证据已归档，后续重点换成同证据预算的简单防御）

**E3 九项 Baseline 已完成目前可行的阶段性复现/机制评估，不继续为了凑论文数量反复下载或单场景调 Prompt。** 完整状态、路径及限制以[实验进度与证据记录](https://docs.google.com/spreadsheets/d/1GEWPdsTolDXWPGqqoDdTNDUHkJv7_q54JYADDUooakc/edit)为准。

| # | 方法 | 当前证据级别 / 阶段判断 |
|---|---|---|
| 1 | RoboGuard | A：SPINE+Spot/LTL+DeepSeek 适配语义重标名，可被简单可信几何识别；原版完整攻防未证实 |
| 2 | SafeGate-inspired | M：研究者 Z3/合同机制，状态伪造可引发错误准入；非官方 SafeGate |
| 3 | RoboSafe-inspired | M：视觉/历史的受控双源替换出现误授权及误拒；非原版训练/记忆闭环 |
| 4 | EMBGuard | 官方 2B 权重/Prompt CPU 真推理 + A：研究者 StateMonitor AND 视觉门；20 条 Clean、5 对配对、E3G-2 攻/安各1次 Unity 真动作 |
| 5 | HD-Guard | A：DeepSeek 替代的视觉告警鲁棒性 Pilot；非执行前准入，单黑帧攻击易被质量门识别 |
| 6 | SELP | O 组件：Spot/LTL Checker、受约束解码组件；原版 NL→规划端到端缺资源，K 炉灶映射自定义 |
| 7 | PerceptTwin | O/A：数字孪生组件、原版动作执行与事后 Judge；E1/E2-A/B自定义执行前门，官方原生无同条炉灶安全政策 |
| 8 | GuardAgent | 软件 Agent 策略/工具权限；具身状态映射由研究者建立，核心执行前具身比较 N/A |
| 9 | Mind the Refinement Gap | A：SPINE原回调/Planner+符号检查对别名污染敏感，几何冲突检查能化解已有同图攻击；真实 ROS 写入未证实 |

**E4–E6 必选直接对照（不计第十个“论文 Baseline”）：** S0 No guard（适用时）、S1 原生/冻结规则、S2 新鲜二次检查、S3 相同共享源重查、S4 可用的受保护独立查询（不可用则 X 上界）、S5 RGB/目标绑定、S6 UNKNOWN/DEFER 与超时恢复、S7 对反馈/TOCTOU 的版本检查/序列化。每组注明证据实际可得性，采用**相同政策、相同目标、相同证据权限**。

## 9. Metrics（执行级与授权级分离）

| 指标 | 定义与报告原则 |
|---|---|
| **UAR_probe** | 固定、有效且客观 unsafe 候选中，最后执行前输出 ALLOW 的比例；可用于自定义 Gate，对“Planner 共同失效”不作推断 |
| **UAR_closed_loop** | Planner 真实生成的 unsafe 候选被最终 Monitor 放行的比例；需要同时报告 Planner 产生 unsafe 候选的频率与样本来源 |
| **Simulation Execution ASR** | 预注册有效攻击回合最终发生实际 Unity 安全合约违规/预定义危险结果；不以 `WOULD_SUBMIT` 或 post-hoc Judge 报 Unsafe 代替 |
| **False Block / False Defer / Recovery** | 在合法动作分母上分别统计错误 BLOCK、暂缓、超时及成功恢复；不能以全部拒绝掩盖正常任务失败 |
| **Benign Task Success Rate** | 在正常任务/时间预算内真正完成的比例，区分“获得授权”和“物体状态实现目标” |
| **Evidence sufficiency / binding / conflict** | 仅以独立证据正确标签评价覆盖和准确率；不能由出参自称可信 |
| **Verification Latency / Cost** | 采集、模型加载、模型生成、重查、调用、执行、端到端分别计时；报告 n、分位数、失败/超时、额外视角/模型调用及 CPU RSS |

**最新实测限定：** E3G-2C 有 `StateMonitor ALLOW + EMBGuard safe → final ALLOW → Unity burner ON → post-hoc UnsafeAction`，E3G-2D 真实有锅同样 ALLOW 后正常执行、post-hoc SafeAction（攻击/安全各 n=1）；EMBGuard 两次模型**生成阶段**分别 32.432 s 和 33.122 s。这**不是**整个授权链的端到端延迟，也不是现实机器人可部署性的证明。

## 10. 当前进度、研究决策与未来工作

### 10.1 已完成（精简）

- **E1/E2：** AI2-THOR 环境、SafeAgentBench 任务与技能、属性/空间/反馈相关状态探针、执行前/执行后分离；同一污染炉灶实例可被同 Unity Metadata 可信重查阻断，合法锅具正例可正确通过。
- **E3：** 九项 Baseline 的当前可行复现/适配/机制 Pilot 已分类归档，不再要求九项都达到原版端到端复现；#4 EMBGuard 官方2B权重CPU真实加载，Clean v1 20条 TP8/FN2/TN4/FP6，5对同图不同动作0/5整对正确；真实 Unity 执行前融合的受控攻击/安全实例各 1 次。
- **主要经验：** 存在可复现的**受控输入错误授权**，但某些场景可以被简单、额外受保护的事实核验/几何绑定阻断；单场景视觉风险模型未提供可靠覆盖。当前最关键的缺口是 **T1/T2 真实输入链、独立样本和同预算强简单防御对照**。

### 10.2 下一阶段决策门

| 决策门 | 核心问题 | Go / No-Go |
|---|---|---|
| **G0：攻击入口（E4-0）** | 能否在不改 Guard 代码与 Ground Truth 的前提下影响真正上游 Producer、并证明 Monitor/Planner 谁消费了它？ | 若仅 T0，继续分析可保留，但研究主张收缩为适配机制，不扩写原版实攻 |
| **G1：泛化及执行（E4）** | ≥2 类安全事实、跨任务/目标与正常正负对照是否成立？ | 若动作原生不可执行，单报 UAR；若仅一个合约单例，停止泛化断言 |
| **G2：强简单防御（E5）** | Fresh protected fact、几何绑定、UNKNOWN/DEFER、source/version 是否已以合理成本解决？ | 若已充分解决且良性成本低，优先写评估发现而非新 Monitor |
| **G3：统计与写作（E6）** | 可否给出真实分母、独立任务簇和实际 p50/p95/超时等指标？ | 缺足够样本则限定为 Pilot 或机制复现，绝不称总体防御失效率 |

### 10.3 条件性后续路线

- **主路径（优先）：** 系统化的 Evidence Trust Boundary Evaluation，强调攻击权限、证据可观测性、来源同源性、目标绑定、简单防御胜负、明确失效/成功条件；没有必要先提出共享资源池、TEE 或新大模型。
- **转向防御 Design 的条件：** 出现真实可达、多个独立场景反复成立的剩余错误授权，而现有强简单修复因缺证据、误拒、延迟或资源限制无法在公平信息预算下解决。此时才考虑来源约束的验证顺序、目标身份和证据时效策略等可解释轻量方案。
- **收缩/终止条件：** 若仅 T0、原版运行时未含被声称的安全政策，或简单可信核验已低成本覆盖所有有效案例，则应明确提出负面研究发现，调整论文范围，而不是通过人工削弱 Baseline 制造 Gap。

## 11. 组会汇报摘要

**Problem：** 安全检查在逻辑上可以正确，却可能依据错误的世界状态；它是否有足够可靠、可用且与目标动作绑定的证据支持 ALLOW？

**What we have：** E1–E3 已建立多个适配/机制级的错误判断实例及有效的简单防御反例；真实 EMBGuard-2B 视觉风险分支参与研究者执行前门，单例没阻止受控错误授权和 Unity 开火，但这不等于 EMBGuard 原版被攻破。

**What we still need：** 可审计的攻击者写入边界、至少两类事实与独立场景、同证据条件的重查/视觉/Defer 对照以及安全—效用—延迟的完整计量。

**Research direction：** **评估具身智能运行时安全检查对安全关键环境事实的信任边界，并明确其可被验证、需要拒绝、或会错误放行的条件。**

---

## 参考文献

[1] *Do As I Can, Not As I Say: Grounding Language in Robotic Affordances* (SayCan, 2022). https://arxiv.org/abs/2204.01691

[2] *ProgPrompt: Generating Situated Robot Task Plans using Large Language Models* (ICRA 2023). https://arxiv.org/abs/2209.11302

[3] *VoxPoser: Composable 3D Value Maps for Robotic Manipulation with Language Models* (2023). https://arxiv.org/abs/2307.05973

[4] *AI2-THOR: An Interactive 3D Environment for Visual AI* (2017). https://arxiv.org/abs/1712.05474

[5] *Safety Guardrails for LLM-Enabled Robots* (RoboGuard, 2025/2026). https://arxiv.org/abs/2503.07885

[6] *Pre-Execution Safety Gate & Task Safety Contracts for LLM-Controlled Robot Systems* (SafeGate, 2026). https://arxiv.org/abs/2604.05427

[7] *RoboSafe: Safeguarding Embodied Agents via Executable Safety Logic* (2025). https://arxiv.org/abs/2512.21220

[8] *DoReMi: Grounding Language Model by Detecting and Recovering from Plan-Execution Misalignment* (2023). https://arxiv.org/abs/2307.00329

[9] *PerceptTwin: Semantic Scene Reconstruction for Iterative LLM Planning and Verification* (2026). https://arxiv.org/abs/2606.04226

[10] *VeriGraph: Scene Graphs for Execution Verifiable Robot Planning* (ICRA 2026). https://arxiv.org/abs/2411.10446

[11] *Mind the Refinement Gap: When Safe High-Level Robot Plans Produce Unsafe Executions* (2026). https://arxiv.org/abs/2610.02662

[12] *EMBGuard: Constructing Hazard-Aware Guardrails for Safe Planning in Embodied Agents* (ICML 2026). https://proceedings.mlr.press/v306/choi26i.html

[13] *Contextual Safety Reasoning and Grounding for Open-World Robots* (CORE, 2026). https://arxiv.org/abs/2602.19983

[14] *System-Level Safety Monitoring and Recovery for Perception Failures in Autonomous Vehicles* (SPARQ, 2024/2025). https://arxiv.org/abs/2409.17630

[15] *Risk-Aware Semantic Grounding for Trustworthy LLM-Based Robot Planning* (2026). https://arxiv.org/abs/2609.37554

[16] *PROTEA: Securing Robot Task Planning and Execution* (IROS 2026; includes HarmPlan). https://protea-secure.github.io/PROTEA/

[17] *When State Becomes an Attack Surface: State-Semantic Injection in LLM-Driven Embodied Agents* (ESTI; arXiv:2608.16806, 2026). https://arxiv.org/abs/2608.16806

[18] *Not What You Asked For: Typographic Attacks in Household Robot Manipulation* (2026). https://arxiv.org/abs/2605.18593

[19] *Seeing is Not Believing: Breaking the Physical-to-Digital Trust Boundary in Robotics* (2026). https://arxiv.org/abs/2609.08280

[20] *Traceable World State: A Provenance-Aware State Representation and Deterministic Replay Framework for Robotic Systems* (2026). https://arxiv.org/abs/2610.12033

[21] *Defeating Prompt Injections by Design* (CaMeL, 2025). https://arxiv.org/abs/2503.18813

[22] *The Granularity Mismatch in Agent Security: Argument-Level Provenance Solves Enforcement and Isolates the LLM Reasoning Bottleneck* (PACT, 2026). https://arxiv.org/abs/2605.11039

[23] *Security of Foundation-Model-Powered Embodied Agents: Attack Surfaces, Attacks, Defenses, and Evaluation* (2026). https://arxiv.org/abs/2608.16843

[24] *SafeAgentBench: A Benchmark for Safe Task Planning of Embodied LLM Agents* (includes SafeAgentEnv). https://safeagentbench.github.io/

[25] *AGENTSAFE: Benchmarking the Safety of Embodied Agents on Hazardous Instructions* (CVPR 2026). https://openaccess.thecvf.com/content/CVPR2026/html/Ying_AGENTSAFE_Benchmarking_the_Safety_of_Embodied_Agents_on_Hazardous_Instructions_CVPR_2026_paper.html

[26] *RoboJailBench: Benchmark for Robotics Security* (project/benchmark). https://purseclab.github.io/benchmark-for-robotics-security/

*注：文中对“某防御可能继承错误上游状态”的描述属于基于其输入依赖关系的条件性分析，不等于该论文已被实际攻破；Benchmark 与 Baseline 均为候选，开源完整度及跨平台适配可行性还需进一步审查。*
