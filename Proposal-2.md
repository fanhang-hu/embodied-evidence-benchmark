# 恶意环境状态污染下具身智能运行时安全验证的信任边界

**Trust Boundaries of Runtime Safety Verification under Adversarial World-State Corruption**  
**研究阶段：** Problem Formulation / Research Gap Verification（尚未确定 Design）  
**用途：** 组会研究方向汇报｜2026 年 10 月

> **核心问题：** 已有具身智能 Safety Monitor 可以检查计划是否符合给定环境状态与安全规则；但当攻击者污染安全检查所依据的环境事实时，这种检查在什么条件下仍然可信？
>
> **当前定位：** 优先分析现有防御的信任假设、攻击下的失效条件及简单修复的有效性；是否需要提出新的防御机制，仍待最小失效验证决定。

## 1. Background

近年来，LLM/VLM 被广泛引入具身智能的高层认知与任务规划。==典型机器人系统接收用户的自然语言目标，通过摄像头、深度传感器或其他感知模块获取环境信息，再将对象类别、属性、空间关系和历史执行反馈整理为 World State（或 Semantic Scene Map），交由 Planner 生成动作序列，并通过 Robot Skills、运动规划器及底层控制器与物理世界交互。==SayCan 将语言模型的语义规划与机器人技能的可执行性关联起来 [1]；ProgPrompt 将环境对象、可用动作和前置条件组织为程序式任务规划 [2]；VoxPoser 利用语言与视觉模型构造空间约束以指导机器人操作 [3]。AI2-THOR 等交互仿真平台使此类“感知—规划—执行—反馈”闭环能够在可控环境中研究 [4]。

与纯数字 Agent 不同，具身 Agent 的错误决定可能转化为真实物理操作，因此任务成功率并不足以描述系统安全性。已有研究在 Planner 与物理执行之间加入运行时安全监控，通过可信规则、形式化约束、动作前置条件、执行状态和实时视觉信息过滤高风险行为。例如，RoboGuard 使用环境相关的 LTL 安全规范审查计划 [5]；SafeGate 对任务施加执行前准入及执行过程中的安全合约 [6]；RoboSafe 结合视觉观察和历史轨迹动态生成安全谓词 [7]。这些工作已经形成较成熟的规划与执行安全检查基础。

然而，安全检查通常依赖某种环境事实：物体是否存在、设备是否打开、目标区域是否允许进入，以及前一步操作是否成功。相关事实可能来自视觉推理、语义地图、状态服务或 Skill 反馈。**状态被及时同步或具有完整的存储记录，不必然意味着其描述的物理事实正确。** 环境事实可能因识别错误、遮挡、过期或主动攻击而失真；更重要的是，Planner 与 Safety Monitor 可能共同依赖同一条受到污染的上游信息。

已有攻击工作表明，这一风险并非纯粹假设。ESTI 通过修改 Planner 可见的环境状态语义，影响规划和执行结果 [17]；物理文字干扰可经由开放词汇感知传播至持久化语义地图，并影响机器人操作 [18]；ROS2 遥测伪造研究进一步揭示，数据在进入受保护的消息通道之前就可能被恶意修改 [19]。因此，本研究暂时聚焦于 **LLM/VLM Planner + Robot Skills 场景中<u>安全关键环境证据的可信边界</u>**，而不是重新构建通用机器人 Planner，也不预设必须使用共享资源池、Evidence Hub、TEE 或系统调用审计。

## 2. Related Work

**Planning Safety and Formal Verification.** RoboGuard [5] 将预设安全规则结合语义 World Model 转换为上下文相关的 LTL 约束，并通过形式化控制合成修正潜在危险计划；SafeGate [6] 通过执行前安全门与 Task Safety Contracts（Guards、Invariants、Abort Conditions）处理危险命令及状态转移。两者说明基于规则的执行准入与安全计划验证已得到充分研究。其重要边界在于：形式化检查可以保证“给定状态和规则下”的逻辑一致性，却不会自动证明输入 World State 真实；RoboGuard 也明确承认严重受损的 World Model 会影响安全保证。

**Runtime Monitoring and Execution Safety.** RoboSafe [7] 使用短期执行轨迹、长期安全记忆和视觉观察形成动态可执行安全谓词，并结合前向预测和后向反思发现潜在风险；DoReMi [8] 通过检测计划与实际执行的偏离来触发恢复；SafeGate [6] 已具备执行前后检查与信息不足时的 Defer 能力。相关方法覆盖了动态监控、状态更新、异常中止与重规划，因此“每一步检查、执行后更新环境”本身并不是新的贡献。其尚待明确的边界是：当当前观察、历史记录或场景快照中出现恶意伪造但看似确定的安全事实时，检查是否仍有足够的独立依据。

**Scene Grounding and Plan Verification.** PerceptTwin [9] 将机器人感知得到的 Semantic Scene Map 重建为交互仿真，用于检验技能前置条件、模拟执行并向 Planner 反馈；VeriGraph [10] 使用由视觉生成的 Scene Graph 约束和修正机器人计划；Mind the Refinement Gap [11] 进一步指出，高层计划即使通过形式化检查，实际执行所隐含的路径或动作效果也可能未被验证。这些研究已覆盖语义建模、执行前仿真及计划—执行一致性。需要区分的是：重建仿真的可靠性取决于其输入场景，场景图内部自洽不等于其所有事实与真实世界一致；同时 PerceptTwin 已能通过安全 Judge 拦截部分误导性标签引发的危险，不能假定它在所有污染攻击下失效。

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

## 4. Threat Model

**System and attack surface.** 我们考虑采用 LLM/VLM Planner、语义环境状态和 Robot Skills 的具身系统。环境信息可以经过感知模型、Scene Graph/World State 服务或执行反馈接口转换为 Planner 与 Safety Monitor 可使用的结构化或文本表示。攻击者希望在可信用户目标不变的情况下，通过污染其中部分安全关键状态，使 Planner 生成危险动作，或使 Safety Monitor 错误地将不安全动作判断为可执行。这一高层攻击面与 ESTI 的环境状态文本污染研究相近 [17]；上游感知地图污染与机器人消息伪造分别有不同的实证支持 [18,19]。

**Attacker capabilities.** 我们暂时假设攻击者能够修改**部分不可信语义状态生产者或状态接口**输出的内容，包括对象属性、空间关系及（扩展场景中的）Skill 反馈。需要区分两个权限层级：（1）仅 Planner-visible State 被篡改，而 Monitor 可能保留独立、受保护的状态来源；（2）Planner 与 Monitor 共同读取的上游 Semantic State 被污染。第二种情况是我们重点关心的候选共同证据失效，但其具体可利用入口需要在后续验证中固定，不应默认攻击者已控制整个机器人。

**Defender assumptions and exclusions.** 我们假设可信用户任务、安全策略、Safety Monitor 的核心逻辑和底层执行器未被攻击者直接修改，并假设至少部分独立观测来源不受攻击者控制，但这些观察未必足够判定所有事实。当前不研究攻击者同时控制全部传感器、直接篡改仿真 Ground Truth、改写物理控制器、破坏可信安全规则或绕过所有执行接口的情形；也暂不讨论端到端 VLA 的内部攻击。AI2-THOR 仿真器的真实状态仅用于离线标注及评估，不能被当作现实部署中 Safety Monitor 天然拥有的“真值接口”。在此边界下，目标是判断哪些动作具有充分安全依据，而不是承诺任意情况下均能恢复物理真相。

## 5. Research Gap

**Gap A — Runtime Safety Verification 的环境事实可信假设。** ESTI [17]、感知语义地图攻击 [18] 和遥测伪造 [19] 已分别说明状态污染有现实攻击路径；RoboGuard [5] 也明确承认准确 World Model 是其重要前提。这说明问题存在，但并非我们首次发现。因此，不能只把“环境状态也可能被攻击”作为论文创新。

**Gap B — 缺乏充分可比的对抗性信任边界评估。** 现有代表性 Guardrail 分别依赖 Semantic World Model、Scene Snapshot、原始视觉、重建仿真或执行历史，其实际可抵抗的攻击权限并不相同 [5–7,9,12,13]。在本轮核查的论文中，尚未找到一项对这些代表性强防御在**统一的上游语义状态污染模型**下，同时评估证据独立性、错误授权和执行级后果的完整对照研究。**这是当前最有依据的候选研究切入点**，但不能声称全领域不存在其他同类工作。

**Gap C — 部分可信证据下的非平凡防御需求。** 对部分场景，可靠的独立查询、重新观察、保守 Defer/Reject 已足够 [6,12–15]；而在证据不完整、同源相关、只覆盖部分安全事实的场景中，现有方案能否同时降低危险执行并保持合法任务能力仍需确认。**这可能成为后续防御方法的空间，但目前尚未证明简单措施不够，更不能预先宣称需要全新算法。**

**当前判断：** Gap B 可以作为信任边界分析和最小失效验证的研究起点；是否进一步走向 Gap C 的新防御机制，取决于后续实验结果。

## 6. Research Questions

**RQ1 — Trust Boundary.** 对象属性、空间关系等安全关键语义事实受到主动污染时，现有 Safety Monitor 在哪些可信输入条件下仍正确拦截，在哪些条件下可能错误放行？

**RQ2 — Failure Mechanism.** 潜在失效主要来自 Planner–Monitor 共享错误来源、独立观察不足、历史记录同源相关，还是计划与实际执行状态之间的信息差异？

**RQ3 — Existing Defenses.** 普通 Pre/Post-check、独立重新感知、受保护状态查询、Defer/Reject 以及现有强 Guardrail 能够解决多大比例的失效？它们对正常任务有什么代价？

**RQ4 — Research Necessity.** 若 RQ1–RQ3 揭示可复现且非平凡的剩余失效，是否存在超出现有简单修复的防御需求及可量化收益？**RQ4 目前只作为条件性后续问题，不预设答案。**

## 7. 实验规划：Benchmark / Dataset / Platform（候选）

建议以 **AI2-THOR / SafeAgentEnv 为一个主闭环平台**，以状态污染攻击和安全任务数据作补充。现成数据集并不保证含有我们需要的“真实事实—污染事实—证据来源—独立核验能力”全部标签，必要时需建立少量受控实例；但不应因此先建设完整的新框架。

| 资源 | 任务覆盖及适用性 | 建议角色 |
|---|---|---|
| **AI2-THOR** [4] | 家庭环境、交互式技能、RGB/Depth、仿真状态及执行结果；可严格分离 Monitor 输入与离线 Ground Truth | **S：主仿真环境** |
| **SafeAgentBench / SafeAgentEnv** [24] | 750 个任务，含安全/危险任务与基于 AI2-THOR 的高层动作执行 | **S：主安全任务集** |
| **ESTI / ESTI-Bench** [17] | 状态语义污染及 Planning/Execution 攻击传播；涉及多种具身平台 | **S：主要攻击依据**；复现条件待核实 |
| **AGENTSAFE / SAFE-THOR** [25] | 1,350 个危险任务，覆盖感知、规划和执行阶段 | **A：阶段化安全评价** |
| **EMBGuardTest / EMBHazard** [12] | 329 个视觉—动作安全测试场景；15.1K 条动作条件训练样本 | **A：视觉安全核验对照**；不等于闭环攻击任务 |
| **HarmPlan / PROTEA** [16] | 1,438 条正常与含隐蔽恶意行为的计划 | **A：Plan Judge 对照**；非原生语义状态污染数据 |
| **RoboJailBench** [26] | 正常/攻击意图及机器人安全评测 | **B：补充泛化**；需审查攻击模型差异 |

**平台扩展：** 如主平台出现显著局限，可用 VirtualHome 研究程序化计划，或借鉴 Habitat/HomeRobot 中的真实感知语义污染路径 [18]。ROS2 + Gazebo/实体机器人用于进一步验证软件消息与物理感知边界，不作为初期必选条件。数据集之间的模型输入、动作空间与攻击方式不相同，不能简单拼接结果。

## 8. Baseline：明确的对照层次

Baseline 的作用是**逐步排除最简单、最强的替代解释**，而不是只罗列 SOTA。建议分为以下四层：

| 层级 | Baseline / 方法 | 实际测试什么 | 优先级与注意事项 |
|---|---|---|---|
| **B0. 攻击基准** | **No Defense**：原始 Planner + Skills | 估计污染状态能够造成多少执行级后果 | **必选**；与无攻击正常任务成对比较 |
| **B1. 普通检查** | **Goal–Plan / Plan–Action Consistency**；**Pre-check / Post-check + 固定安全规则** | 判断计划或执行是否与当前状态/规则一致，是否存在共同错误事实 | **必选**；检查结果依赖被提供的状态 |
| **B2. 简单而强的修复** | **Fresh Re-observation**（获取新 RGB/Depth 后再检查）；**Protected State Query**（仅在合理可用时）；**Fail-Closed Defer/Reject** | 重新观察、独立状态来源和一律保守暂停是否已充分防御 | **必选**；必须同时报告正常任务损失；Protected Query 不可假装在所有机器人上存在 |
| **B3a. 规划与执行 Guardrail** | **RoboGuard** [5]、**SafeGate** [6]、**RoboSafe** [7] | 形式化规则、执行安全合约、动态安全谓词和历史反馈 | **核心强基线候选**；优先核查可复现性与实际输入权限 |
| **B3b. 场景与视觉核验** | **PerceptTwin** [9]、**EMBGuard** [12]、**CORE** [13] | 重建仿真、当前视觉核验及不确定性感知能否纠正状态污染 | **核心强基线候选**；不同接口可能需要适配，不能把弱化复现称为原论文完整系统 |
| **B3c. 相关补充** | **Risk-Aware Semantic Grounding** [15]、**PROTEA** [16] | 语义冲突/歧义处理和 Plan-level 恶意行为判断 | **辅助比较**；不一定与闭环执行攻击直接对齐 |
| **B4. 分析上界** | **Oracle Ground Truth Checker** | 已知真实关键事实时，理想检查能够达到什么结果 | **仅用于离线分析**；不是现实可部署的防御 |

**公平对比原则：** 固定正常任务、攻击样本和安全约束；明确不同方法究竟访问了哪一级环境信息；不能故意取消原方法本来拥有的独立视觉或可信规则。如果某论文无法在相同平台直接运行，可以只比较与其核心机制一致的可复现实验设置，并明确标记为机制适配版本。

## 9. Metrics：评价指标与解释

| 评价维度 | 指标 | 需要回答的问题 |
|---|---|---|
| **攻击传播** | Planning ASR、**Execution ASR** | 污染是否真正从 Plan 传递到危险执行；二者必须分开 |
| **执行安全** | Attack Prevention Rate、Unsafe Action Rate | 防御是否在危险动作发生前阻止攻击，而不是仅在事后告警 |
| **正常任务效用** | **Benign Task Success Rate**、**False Block Rate** | 是否因为过度拒绝而牺牲合法任务执行 |
| **风险/污染识别** | Precision、Recall、FPR、F1 | 对真正不安全动作或污染事实的判别质量；必须先固定标签粒度 |
| **证据可核验性** | Evidence Attribution Accuracy、Verification Coverage、Evidence Sufficiency Accuracy | 能否定位依赖来源、是否存在可用核验、何时应返回 Unknown |
| **性能与交互成本** | **Verification Latency**（p50/p95/p99）、VLM 调用次数、额外观测次数、CPU/内存 | 额外安全监控是否具有在线可用性 |
| **暂停与恢复** | Defer Rate、Recovery Success Rate、Task Completion After Verification | 暂停之后能否恢复，还是永久拒绝任务 |

**最重要的四项：Execution ASR、Benign Task Success Rate、False Block Rate、Verification Latency。** Attack Prevention Rate 必须依据真实危险执行是否被阻止计算；不能把“动作没有发生”（例如本来就无法执行）一律当作防御成功。Defer 和 Reject 应单独计量，避免一律拒绝获得表面上很好的安全成绩。

## 10. 当前进度与下一步：Minimum Failure Validation

| 工作项 | 当前进度 |
|---|---|
| Background / Attack Surface | 已基本明确 |
| Related Work | 已完成代表性文献及机制的初步核查 |
| Threat Model | 已有工作性定义；具体可攻击接口仍需固定 |
| Research Gap | **Gap B 有调研依据，但代表性强防御的非平凡失效尚未实测** |
| Design | **尚未确定，也暂不提前设定模块** |
| 实验结果 | 尚未开展 |

**下一步：最小失效验证。** 先完成已有实现的输入与权限审计，再用少量代表性场景做针对性实测，而非立即建造完整系统：

1. **确定攻击入口。** 明确是 Planner-only 文本接口，还是 Planner 与 Monitor 共同依赖的上游语义来源；保留真实、有限的攻击者权限。
2. **确认强防御输入。** 核查 RoboGuard、SafeGate、RoboSafe、PerceptTwin、EMBGuard 等在对应配置下正常可访问的状态、视觉和策略。
3. **做最小交叉验证。** 至少比较正常状态、仅 Planner 状态污染、共享上游状态污染，以及污染后可独立重新观察这几种条件；观察错误放行和错误拒绝。
4. **优先测试简单修复。** 如果可信状态查询、重新观察或保守 Defer 已充分解决，并保持合理任务效用，则不应强行提出复杂新方法。
5. **决定研究路线。** 若发现跨场景、可复现的信任边界失效，可发展为系统性安全分析/Benchmark；只有当已有简单和强防御仍存在有意义的剩余问题时，才进一步研究新的防御 Design。

**退出条件：** 若在合理攻击与可信观察假设下，强基线或简单修复已经充分解决目标攻击，则应收缩或改变 Research Problem，而不是通过削弱 Baseline 人为制造 Gap。

## 11. 组会总结

**Background：** LLM/VLM 具身 Agent 依赖 World State 规划与执行物理任务，已有 Guardrail 对 Plan 和动作提供运行时安全检查。

**Motivation：** 安全检查可以在逻辑上正确，却依赖错误环境事实；主动语义状态污染可能使 Planner 与 Monitor 共同得出错误的安全判断。

**Threat Model：** 攻击者控制部分上游语义状态或反馈接口，不控制可信用户目标、安全规则、底层执行器和所有独立观察；仿真 Ground Truth 仅用于评价。

**Research Gap：** 现有规划验证、视觉核验和运行时安全方法已相当成熟；它们在统一上游状态污染条件下的**证据信任边界、错误授权及执行级安全后果**仍值得系统性评估。是否需要新的防御算法尚未确定。

**当前目标：** 先回答“已有最强防御何时会失效，以及简单检查为什么不够”；之后再决定做安全分析论文还是防御方法论文。

**一句话总结：** **我们不是重新提出一个 Safety Monitor，而是研究当环境证据可能受到恶意污染时，已有 Safety Monitor 的安全判断在什么条件下值得信任。**

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
