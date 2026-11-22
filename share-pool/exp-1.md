# 具身智能 Planning Runtime Security：实验规划

**暂定研究方向：** Trust Boundaries of Runtime Safety Verification under Adversarial World-State Corruption  
**当前阶段：** Research Gap Validation / Minimum Failure Validation  
**文档目的：** 通过对抗性环境状态污染实验，判断现有 Safety Monitor 是否存在具有代表性的错误授权，以及重新感知、可信查询、保守拒绝等简单防御是否已足够。本文为**候选实验规划**，不包含已完成实验结果，也不预设新的系统 Design。

---

## 1. 实验目标与优先级

现阶段不以证明新方法优于 Baseline 为目标，而是建立以下证据链：

**真实的上游语义污染 → 现有安全检查的具体失效 → 简单防御的能力边界 → 是否需要进一步提出新方法。**

| 优先级 | 实验 | 核心问题 | 预期作用 |
|---|---|---|---|
| **P0** | **E1. Shared-State Failure** | Planner 与 Safety Monitor 共享错误 World State 时，是否会错误授权危险动作？ | 确认共同证据失效是否真实存在 |
| **P0** | **E2. Independent Evidence / Simple Defenses** | 重新感知、独立查询、来源检查、保守拒绝是否能阻止攻击？ | 判断问题是否可被简单措施解决 |
| **P1** | **E3. Strong Defense Comparison** | RoboGuard、SafeGate、RoboSafe、EMBGuard、PerceptTwin 等是否仍有具体的安全边界？ | 确认已有强防御的覆盖范围 |
| **P1** | **E4. Generalization** | 失效是否跨对象属性、空间关系及不同任务出现？ | 判断是否只是单一案例 |
| **P2** | **E5. Evidence Reliability** | 证据来源依赖、冲突、过期或缺失怎样影响安全判断？ | 支持原因归因与证据可信性分析 |
| **P2** | **E6. Safety–Utility–Cost** | 安全阻止、正常任务能力和核验成本如何权衡？ | 支持后续方法必要性与实际可用性分析 |

**优先决策顺序：E1 → E2 → E3 → E4。** 如果 E1 没有发现非平凡失效，或 E2 的简单防御已充分解决，应及时调整 Research Problem，而不是继续构造复杂系统。

---

## 2. 仿真平台（Simulation Platforms）

建议采用**一个主闭环仿真平台、一个辅助计划层平台、一个后续扩展平台**。

| 平台 | 能力与特点 | 实验用途 | 优先级 |
|---|---|---|---|
| [AI2-THOR / iTHOR](https://ai2thor.allenai.org/) | 家庭场景、对象属性与关系、交互动作、RGB/Depth、结构化 Metadata | **主平台**；区分真实状态、污染状态和执行结果 | **S** |
| [SafeAgentEnv / SafeAgentBench](https://safeagentbench.github.io/) | 基于 AI2-THOR 的高层动作与安全任务执行环境 | 主闭环任务与安全评估 | **S** |
| [VirtualHome](https://www.virtual-home.org/) | 家庭程序、环境图、动作序列 | 低成本的 Planning / Scene Graph 污染验证 | A |
| [ProcTHOR](https://procthor.allenai.org/) | 程序化生成室内场景 | 未见场景与场景变化泛化 | B |
| [Habitat / HomeRobot](https://aihabitat.org/) | 视觉感知、家居导航、语义地图与操作任务 | 上游感知错误传播至持久化语义状态的扩展 | B |
| ROS2 + Gazebo / 真实机器人 | 更接近真实传感器、通信和执行链路 | 真实状态接口、反馈伪造与系统扩展 | 后续 |

### 2.1 主平台中必须区分的三种信息

| 数据通道 | 内容 | 使用边界 |
|---|---|---|
| **True World State** | 仿真器内部的真实物体与环境状态 | 仅作 Ground Truth、标注与最终执行评价 |
| **Planner-visible State** | Planner 所获得的对象属性、空间关系、当前阶段与执行状态 | 主要状态污染攻击对象 |
| **Monitor-visible Evidence** | Safety Monitor 按原有机制可读取的语义状态、RGB/Depth、历史记录或其他观察 | 用于判断真实防御能力，不应被人为剥夺 |

**公平性要求：** AI2-THOR `event.metadata` 可能包含当前摄像头不可见的真实对象状态，不能未经说明直接提供给被测 Monitor；否则相当于使用 Oracle。若某 Baseline 在原生设置中确有受保护的独立状态接口，必须保留并单独说明。

**建议组合：AI2-THOR + SafeAgentEnv 作为闭环主平台；ESTI 作为攻击形式与评测协议的重要参考。** AI2-THOR（模拟器）、SafeAgentEnv（任务执行环境）和 ESTI（攻击研究/评测依据）并不是同类、可相互替代的资源。

---

## 3. Benchmark / Dataset 候选

### 3.1 Benchmark 分类与优先级

| Benchmark / Dataset | 核心内容 | 在本研究中的用途 | 优先级 |
|---|---|---|---|
| [ESTI / ESTI-Bench](https://arxiv.org/abs/2608.16806) | 环境状态文本污染；涉及 ProgPrompt/VirtualHome、VoxPoser/RLBench、AI2-THOR 等设置 | **主要攻击依据**，关联 Planning 与 Execution 攻击效果 | **S** |
| [SafeAgentBench](https://safeagentbench.github.io/) | 750 个安全相关任务（此前调研归纳为其中 450 个危险任务） | 任务级闭环安全性、正常任务执行与效用 | **S** |
| [AGENTSAFE / SAFE-THOR](https://openaccess.thecvf.com/content/CVPR2026/html/Ying_AGENTSAFE_Benchmarking_the_Safety_of_Embodied_Agents_on_Hazardous_Instructions_CVPR_2026_paper.html)（CVPR 2026） | 45 个场景、1,350 个危险任务、9,900 条指令（据此前调研） | Perception / Planning / Execution 阶段性安全分析 | A |
| [EMBGuardTest](https://proceedings.mlr.press/v306/choi26i.html)（ICML 2026） | 329 个视觉—动作风险场景、7 类物理风险（据此前调研） | 独立视觉 Guardrail 的风险识别与误报评价 | A |
| [HarmPlan / PROTEA](https://protea-secure.github.io/PROTEA/)（IROS 2026） | 1,438 个正常/恶意计划、6 类危险、3 个难度（据此前调研） | Plan-level Safety Judge 对照 | A |
| [RoboJailBench](https://purseclab.github.io/benchmark-for-robotics-security/) | 恶意/正常意图配对、多类别安全违规后果 | 攻击效果与正常任务效用权衡 | B |
| [Risk-Aware Semantic Grounding / TRUST-NAV](https://arxiv.org/abs/2609.37554) | 语义歧义、幻觉与冲突相关导航样本 | 语义风险识别补充评价 | B |

> **适配限制：** 上述数据规模为此前文献调研记录，具体版本、标注格式与公开可下载程度应以实际获取的资源为准。它们并不全部原生包含“合法任务 + 恶意环境状态污染”的配对实验。HarmPlan、EMBGuardTest 等主要适合各自的计划级或视觉级子任务，不能直接视为完整闭环 World-State Corruption Benchmark。ESTI 的官方完整实现及所需攻击数据能否直接复现，也应单独确认。

### 3.2 实验数据的五类必要条件

| 类型 | 定义 | 主要作用 |
|---|---|---|
| **D0. Clean State** | 未被污染的正常状态 | 正常任务能力、误报及执行成功率基准 |
| **D1. Planner-only Corruption** | 只污染 Planner 可见的语义信息 | 测试独立 Monitor 能否阻止攻击 |
| **D2. Shared Upstream Corruption** | 污染 Planner 和 Monitor 共同依赖的上游状态来源 | 测试共同证据失效 |
| **D3. Partial Independent Evidence** | 存在部分未被攻击、但可能不充分的独立观察 | 测试重新感知/补充核验的真实能力 |
| **D4. Unverifiable / Conflicting Evidence** | 关键事实无法确认或多源信息冲突 | 测试保守暂停、错误放行及任务效用 |

### 3.3 需要补充的标注字段

- **真实状态：** 攻击前 Ground Truth、关键物体/空间关系及真实安全属性。
- **攻击信息：** 被污染的字段、伪造值、攻击者控制的组件与持续时间。
- **证据来源：** 各条信息由哪个传感器/语义处理组件产生，是否共享同一个受攻击来源。
- **观察能力：** Monitor 能访问哪些独立观测；安全关键事实是否可观测、可确认。
- **安全条件：** 候选动作依赖的关键事实及违反时的安全后果。
- **决策与结果：** Planner 动作、Monitor 的 Allow/Block/Defer、执行结果及攻击是否达成。

**数据建设原则：** 可在已有任务和场景基础上补充少量受控污染样本，不以从头建设大型新数据集为第一目标。

---

## 4. 攻击与证据条件（实验自变量）

### 4.1 攻击类型

| 攻击类别 | 操纵对象 | 优先级 |
|---|---|---|
| **A. Object Attribute Corruption** | 开关状态、对象类别、危险属性 | **S** |
| **B. Spatial / Relational Corruption** | 对象位置、包含关系、目标区域、空间关系 | **S** |
| **C. Affordance / Preconditions Corruption** | 可交互属性、操作条件、任务阶段相关状态 | A |
| **D. Execution Feedback Corruption** | Skill 成功标志、后续执行状态、完成反馈 | B（后续） |

第一阶段优先 A、B：它们更能体现高层环境语义信息对 Planner 与 Safety Monitor 的影响。反馈伪造可作为阶段扩展，不应默认与对象语义污染完全同一种攻击能力。

### 4.2 攻击覆盖范围

| 设置 | Planner 获得的信息 | Monitor 获得的信息 | 研究目的 |
|---|---|---|---|
| **T0. Clean** | 正常状态 | 正常状态及原有观察 | 设立无攻击基准 |
| **T1. Planner-only** | 被污染状态 | 保有原方案的独立证据 | 衡量独立监控价值 |
| **T2. Shared-state** | 被污染状态 | 共享污染的语义来源，且保留原方案其他观察 | **共同上游污染能否导致错误授权** |
| **T3. Shared-state + Partial Observation** | 被污染状态 | 共享污染来源；剩余独立观察只可确认部分事实 | **复杂但合理的信任边界** |

### 4.3 观察与证据条件

- **Fully Observable：** 安全关键事实可通过独立、可靠的观察确认。
- **Partially Observable：** 仅能获得部分有关事实的观察。
- **Occluded / Unverifiable：** 当前无法确定某项关键事实。
- **Correlated Evidence：** 多条记录来自同一个可能被攻击的源，不能视为独立投票。
- **Conflicting Evidence：** 不同信息源对同一事实给出矛盾结果。

还可以区分**一次性污染**与**跨多步持续污染**。不要把多次读取同一个虚假缓存当成多个独立证据。

---

## 5. Baseline：明确分类与比较目的

### 5.1 基础对照：无防御与通用检查

| 编号 | Baseline | 核心检查方式 | 对照问题 |
|---|---|---|---|
| **B0** | No Defense | Planner 直接执行候选动作 | 无防御时的攻击基准 |
| **B1** | Goal–Plan Consistency | Plan 是否遵循用户目标 | 目标一致性是否足够 |
| **B2** | Plan–Action Consistency | Skill 是否与当前 Plan 一致 | 动作一致性是否足够 |
| **B3** | Pre-execution Rule Check | 根据现有状态事实与规则判断能否执行 | 简单执行前检查是否足够 |
| **B4** | **Pre/Post-check** | 执行前检查、执行后更新和复查 | **共享状态更新方案是否已充分解决** |
| **B5** | LLM-as-a-Judge | 使用另一个模型审核动作或计划 | 模型级独立是否足够 |

B1–B5 为**按机制定义的实验对照**，不是独立发表论文的同名完整系统。B4 特别重要，是最直接的简单替代方案。

### 5.2 简单修复：必须比较的非复杂防御

| 编号 | Baseline | 核心能力 | 对照问题 |
|---|---|---|---|
| **B6** | **Fresh Observation** | 对关键事实重新取得 RGB/Depth 等当前观察 | 重新感知是否足够 |
| **B7** | Independent Observation Check | 利用不受同一攻击控制的独立证据 | 独立证据能否纠正错误 |
| **B8** | Source Consistency Check | 检查状态记录来源、版本及依赖 | 简单来源核验是否足够 |
| **B9** | **Conservative Defer / Reject** | 无法确认安全时暂停或拒绝 | 保守策略是否可同时保障安全与正常任务 |
| **B10** | Trusted State Query | 从真实可部署且受保护的状态接口查询关键事实 | 可信查询是否已直接解决问题 |
| **B11** | Oracle Ground Truth Checker | 直接读取仿真器内部真实状态 | 理想化上界；不可作为普通现实防御 |

**必须区分 B10 与 B11：** B10 只有在系统确实提供可部署、受保护、充分准确的查询接口时才是现实可比 Baseline；B11 只用于理论上界和分析，不能向普通 Monitor 泄露 Oracle 数据。

### 5.3 已发表强防御：按机制进行比较

| 方法 | 关键机制 | 我们要测试什么 | 优先级 |
|---|---|---|---|
| [RoboGuard](https://arxiv.org/abs/2503.07885) | 语义 World Model + LTL 安全约束 | 形式化 Plan Safety 对污染状态的依赖 | **S** |
| [SafeGate](https://arxiv.org/abs/2604.05427) | Safety Contracts、执行准入与状态复查 | Guard、Defer、Post-check 是否足够 | **S** |
| [RoboSafe](https://arxiv.org/abs/2512.21220) | RGB + 历史记忆 + 动态安全谓词 | 重新视觉检查能否纠正上游污染 | **S** |
| [EMBGuard](https://proceedings.mlr.press/v306/choi26i.html) | Visual Observation + Action 风险判断 | 独立视觉风险核验的能力边界 | **S** |
| [PerceptTwin](https://arxiv.org/abs/2606.04226) | 语义场景仿真 + Skill Preconditions + Judge | 仿真是否继承错误场景事实 | A |
| [Risk-Aware Semantic Grounding](https://arxiv.org/abs/2609.37554) | 语义歧义、幻觉与冲突检查 | 内部自洽但错误的状态能否被发现 | A |
| [CORE](https://arxiv.org/abs/2602.19983) | 视觉语义约束 + 感知不确定性 | 其误差假设在主动攻击下的适用性 | B |

**首批建议：RoboGuard、SafeGate、RoboSafe、EMBGuard 四类强防御机制；按可用实现情况扩展 PerceptTwin。** 不能假设每篇工作都能无修改地运行于同一平台，也不能将弱化版适配等同于原论文完整方法。若某方法对目标任务并不适用，应作为独立子实验或机制级对照，明确范围。

### 5.4 其他参考方法：角色不同，不宜强行混合

| 方法 | 定位 | 使用方式 |
|---|---|---|
| [PROTEA](https://protea-secure.github.io/PROTEA/) | Plan-level Safety Judge | 静态计划审核辅助实验 |
| [Traceable World State](https://arxiv.org/abs/2610.12033) | 状态来源、版本和完整性管理 | 来源管理机制参考，不是通用危险动作判别器 |
| [PACT](https://arxiv.org/abs/2605.11039) | 工具参数来源追踪及执行权限控制 | 参考来源授权思想；原生任务并非机器人物理状态验证 |
| [ESTI](https://arxiv.org/abs/2608.16806) | 攻击研究 | 攻击设置/攻击 Baseline，**不是防御** |

---

## 6. Metric：评价指标与统计口径

### 6.1 核心指标（首批必须报告）

| Metric | 建议统计含义 | 优先级 |
|---|---|---|
| **Planning ASR (P-ASR)** | 攻击诱导 Planner 产生目标恶意计划的比例 | **S** |
| **Execution ASR (E-ASR)** | 攻击目标经仿真实际执行后达成的比例 | **S** |
| **Unsafe Authorization Rate (UAR)** | 已标注为危险的候选动作中被 Monitor 放行的比例 | **S** |
| **Attack Prevention Rate (APR)** | 对无防御下本可成功的攻击，防御阻止其危险执行的比例 | **S** |
| **Benign Task Success Rate (BTSR)** | 正常合法任务最终成功的比例 | **S** |
| **False Block Rate (FBR)** | 安全且可执行的候选动作被错误阻止的比例 | **S** |
| **Verification Latency** | 核验引入的响应延迟（p50/p95/p99） | A |

**优先联合报告：UAR、E-ASR、BTSR、FBR。** UAR 直接对应本研究的错误安全授权问题；E-ASR 衡量攻击最终是否实现。监控器放行危险动作，但动作因执行器失败而未完成时，可能 **UAR 高而 E-ASR 低**，两者不能混用。

对 APR 应固定分母，优先以无防御下原本可执行、可成功且可归因的攻击集合计算条件防御率，同时报告所有样本上的原始结果，避免选择性分母夸大效果。

### 6.2 证据、恢复及成本指标（后续）

| Metric | 评价目标 | 优先级 |
|---|---|---|
| Evidence Attribution Accuracy | 识别被污染的关键事实/来源 | A |
| Evidence Sufficiency Accuracy | 判断证据是否足以支持安全授权 | A |
| Verification Coverage | 具备独立核验依据的安全关键事实比例 | A |
| Conflict Detection Recall | 能否识别已标注的相互冲突证据 | A |
| **Correct Abstention Rate** | 无法确认安全时能否正确暂停 | A |
| **False Defer Rate** | 正常且证据充分的动作被不必要暂停 | A |
| Verification Calls / Cost | 额外观察、模型调用和资源成本 | B |
| Recovery Success Rate | 暂停/重新感知后最终完成合法任务的比例 | B |

> 对于被 Block 或 Defer 而没有实际执行的动作，可以使用标注的安全前置条件评价 UAR、FBR 等授权指标，但不能把“未发生真实执行”直接计作已经观测到的执行后果。Defer 必须与永久 Block、最终恢复成功分别统计。

### 6.3 关键评价原则

- **不能只报告低 E-ASR：** 永远拒绝全部动作也能使危险执行归零，却可能摧毁正常任务效用。
- **区分 Plan、Authorization、Execution：** 计划受攻击、监控器错误授权及最终物理执行成功是不同阶段。
- **分事实类别与攻击权限报告：** 对象属性、空间关系等应分别列出，避免平均值掩盖局部失效。
- **提供统计不确定性：** 重复运行、报告置信区间，并固定随机性与攻击样本选择规则。

---

## 7. E1–E6 实验分组与输出表

| 实验 | 主要自变量 | 重点 Baseline | 主要指标 | 预期回答 |
|---|---|---|---|---|
| **E1. Shared-State Failure** | Clean / Planner-only / Shared-state | B0–B5 | UAR、P-ASR、E-ASR | 共享污染是否真的导致错误授权？ |
| **E2. Independent Evidence** | 独立观察可用性、证据覆盖与相关性 | B6–B11 | UAR、BTSR、FBR、Correct Abstention | 简单防御是否已足够？ |
| **E3. Strong Defenses** | 不同 Guardrail 的正常输入与可信权限 | RoboGuard、SafeGate、RoboSafe、EMBGuard、PerceptTwin | UAR、E-ASR、BTSR、FBR | 已有强防御的实际边界？ |
| **E4. Generalization** | 属性/关系/动作条件、场景和任务长度 | E1–E3 代表方法 | 分类别 UAR/E-ASR/BTSR | 是否有普遍性？ |
| **E5. Evidence Reliability** | 来源依赖、冲突、过期、缺失 | Source Check、Fresh Observation 等 | Attribution、Sufficiency、Recall/FPR | 失效机制是什么？ |
| **E6. Safety–Utility–Cost** | 不同检查、暂停与重新观察策略 | Always-Defer、Fresh Observation、强防御 | BTSR、FBR、Defer、Latency、Calls | 安全、效用与成本如何权衡？ |

### 7.1 表 A：攻击权限与错误授权

| Method | Clean FBR ↓ | Planner-only UAR ↓ | Shared-state UAR ↓ | Partial-evidence UAR ↓ |
|---|---:|---:|---:|---:|
| Pre/Post-check | 待测 | 待测 | 待测 | 待测 |
| RoboGuard | 待测 | 待测 | 待测 | 待测 |
| SafeGate | 待测 | 待测 | 待测 | 待测 |
| RoboSafe | 待测 | 待测 | 待测 | 待测 |
| EMBGuard | 待测 | 待测 | 待测 | 待测 |

### 7.2 表 B：简单防御的安全性—效用—成本

| Method | Execution ASR ↓ | Benign Success ↑ | False Block ↓ | Defer Rate | Latency ↓ |
|---|---:|---:|---:|---:|---:|
| Fresh Observation | 待测 | 待测 | 待测 | 待测 | 待测 |
| Source Check | 待测 | 待测 | 待测 | 待测 | 待测 |
| Conservative Defer | 待测 | 待测 | 待测 | 待测 | 待测 |
| Strong Existing Guardrail | 待测 | 待测 | 待测 | 待测 | 待测 |

### 7.3 表 C：不同安全事实类型的失效

| Fact Type | Pre/Post-check UAR ↓ | Visual Guardrail UAR ↓ | Best Applicable Defense UAR ↓ |
|---|---:|---:|---:|
| Object Attribute | 待测 | 待测 | 待测 |
| Spatial Relation | 待测 | 待测 | 待测 |
| Affordance / Preconditions | 待测 | 待测 | 待测 |
| Execution Feedback（扩展） | 待测 | 待测 | 待测 |

表中“待测”不是预测结果；如果某个强方法不支持某类动作或证据接口，应标注 N/A 与具体原因，而不是填入不公平比较的数字。

---

## 8. 公平性、可复现性与数据质量

| 要求 | 理由 |
|---|---|
| **相同任务与初始环境状态** | 排除场景难度差异 |
| **固定 Planner 与 Robot Skills 的基础条件** | 避免把规划器或执行器差异误认为 Monitor 差异 |
| **正常/攻击样本配对** | 区分攻击诱发失败与普通执行失败 |
| **保留 Baseline 原有独立观察能力** | 不能通过削弱强防御来制造漏洞 |
| **明确攻击者控制的证据来源** | 保证 Threat Model 可信、可解释 |
| **Ground Truth 不泄露给被测方法** | 防止 Oracle 不公平优势 |
| **分类记录失败原因** | 区分错误授权、正确拒绝、感知不足、执行器失败 |
| **分类别统计、重复测试与置信区间** | 避免偶然结果与总体平均掩盖失效 |
| **标注实现状态** | 区分原论文完整实现、可复现实验、机制级简化版本 |

---

## 9. Go / No-Go：何种结果支持继续研究？

| 结果 | 研究判断 |
|---|---|
| 共享状态污染导致多个现有 Monitor 错误授权 | 支持共同失效的现实性 |
| 可信独立查询能完整解决所选场景 | 说明无需为该场景另建复杂核验系统 |
| 重新感知或现有视觉 Guardrail 已可靠拦截 | 新方法必要性降低 |
| 保守拒绝能阻止攻击，但显著降低合法任务完成率 | 可能存在安全—可用性权衡空间 |
| 强防御在有限独立证据条件下仍有明显误授权 | **最有力地支持继续研究证据可信性问题** |
| 失效仅在单一物体或人为限制方法输入时出现 | 不足以支持广泛 Research Gap |
| 多类语义事实/任务均存在相似信任边界失效 | 增强系统性研究与泛化的说服力 |

**注意：** 发现现有防御错误授权，不等于已经证明必须设计新算法。还需要说明其安全风险为什么不能由受保护状态查询、重新感知或合理的保守暂停充分解决。

---

## 10. 分批实施与当前阶段重点

### 第一批：Research Gap 验证（必须先做）

- **实验：** E1 + E2。
- **主要资源：** AI2-THOR / SafeAgentEnv；ESTI 类环境状态污染；少量受控状态样本。
- **关键对照：** No Defense、Pre/Post-check、Fresh Observation、Source Check、Conservative Defer、Trusted Query（若现实可用）。
- **目标：** 明确是否存在非平凡的错误授权，以及简单方案的能力边界。

### 第二批：强防御与普遍性验证

- **实验：** E3 + E4。
- **重点对象：** RoboGuard、SafeGate、RoboSafe、EMBGuard；根据实际适配条件扩展 PerceptTwin。
- **任务覆盖：** 对象属性、空间关系、不同场景与多步任务。
- **目标：** 判断是否已经被强方法解决，以及问题是否可推广。

### 第三批：确认研究问题后再扩展

- **实验：** E5 + E6，以及可能的新防御对照、消融、跨平台泛化。
- **目标：** 若前两批确认存在值得解决的失效，再研究证据可靠性与安全—效用—成本权衡。

---

## 11. 组会总结

- **当前最重要的实验：** E1（共享污染导致的错误授权）和 E2（简单独立核验是否足够）。
- **主平台：** AI2-THOR + SafeAgentEnv；以 ESTI 的语义状态攻击为重要参考。
- **主攻击：** 对象属性与空间关系污染；反馈伪造作为后续扩展。
- **关键 Baseline：** Pre/Post-check、Fresh Observation、Conservative Defer，以及 RoboGuard、SafeGate、RoboSafe、EMBGuard。
- **关键 Metric：** UAR、Execution ASR、Benign Task Success Rate、False Block Rate；另报告 Defer 和核验延迟。
- **Go / No-Go 标准：** 若强防御存在可推广的错误授权，而且简单可信查询、重新感知或保守拒绝不能在合理任务效用下充分解决，再考虑提出新的防御方法。

**核心结论：实验的目的不是先证明我们的方法更好，而是先证明是否存在一个真实、非平凡、已有方法仍未充分解决的安全问题。**

---

## 参考资源与论文链接

以下按用途列出主要文献与公开资源（非 BibTeX；具体发表版本与代码状态以对应页面为准）。

**攻击与基准：** [ESTI: Environment State-Text Injection Attack](https://arxiv.org/abs/2608.16806)；[SafeAgentBench](https://safeagentbench.github.io/)；[AGENTSAFE](https://openaccess.thecvf.com/content/CVPR2026/html/Ying_AGENTSAFE_Benchmarking_the_Safety_of_Embodied_Agents_on_Hazardous_Instructions_CVPR_2026_paper.html)；[HarmPlan / PROTEA](https://protea-secure.github.io/PROTEA/)；[RoboJailBench](https://purseclab.github.io/benchmark-for-robotics-security/)。

**安全防御：** [RoboGuard](https://arxiv.org/abs/2503.07885)；[SafeGate](https://arxiv.org/abs/2604.05427)；[RoboSafe](https://arxiv.org/abs/2512.21220)；[PerceptTwin](https://arxiv.org/abs/2606.04226)；[EMBGuard](https://proceedings.mlr.press/v306/choi26i.html)；[CORE](https://arxiv.org/abs/2602.19983)；[Risk-Aware Semantic Grounding](https://arxiv.org/abs/2609.37554)。

**证据来源与权限：** [Traceable World State](https://arxiv.org/abs/2610.12033)；[PACT](https://arxiv.org/abs/2605.11039)。

**仿真平台：** [AI2-THOR](https://ai2thor.allenai.org/)；[VirtualHome](https://www.virtual-home.org/)；[ProcTHOR](https://procthor.allenai.org/)；[Habitat](https://aihabitat.org/)。
