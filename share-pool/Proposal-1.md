# 具身智能 Cognition / Planning 运行时安全监控：组会汇报方案

**暂定研究方向：** Trusted Evidence-Grounded Runtime Security for Embodied Planning  
**研究对象：** LLM/VLM Planner + Robot Skills；优先研究显式任务规划，暂不直接研究完全端到端 VLA。  
**研究定位：** 面向恶意环境证据污染的 Cognition / Planning 在线安全监控与执行前防御。

## 一、研究目标与核心问题

- **研究问题：** 具身 Agent 的 Planner 可能依据被攻击者污染的环境状态生成危险计划；如果 Safety Monitor 使用相同的错误环境信息，规划与验证可能同时失效。
- **核心目标：** 在高风险动作执行前，判断规划所依赖的安全关键事实是否具有足够可靠的证据，并据此选择 **Allow / Re-verify / Block / Replan**。
- **与一般一致性检查的区别：** Goal–Plan、Plan–Action 一致性可能均通过，但“支持规划安全结论的事实”仍然是错误的；因此需要检查**证据来源、依赖关系和可核验性**。

## 二、三个攻击场景

1. **A. 环境状态污染：** 攻击者将危险化学品描述为普通清洁剂，Planner 基于错误的 World State 产生危险放置计划，而 Goal–Plan / Plan–Action Consistency 可能仍然通过。
2. **B. Planner–Monitor 共同证据失效：** Planner 和 Safety Monitor 使用同一份受污染的环境事实，二者均判断危险计划安全；两个独立模型并不意味着拥有独立可信的证据。
3. **C. 数字执行反馈伪造：** 柜门实际上未关闭，但 Skill 返回 `door_closed=true`，使 Planner 错误继续执行；仅讨论数字反馈被伪造，**不要求防御任务正常完成后又遭外力改变的物理状态**。

**阶段重点：** 第一阶段优先 A、B；C 作为接入 ROS / Syscall / 物理执行监控后的扩展。

## 三、可信资源共享池是否必要？

**建议采用逻辑上的可信信息管理机制，不必一开始构建复杂的共享资源系统，也不必强制使用 TEE。**

将其定义为 **Trusted Evidence Hub（可信证据中心）**：管理可信用户目标、安全策略、环境状态记录、历史执行、证据来源、状态版本与访问权限。配合独立的 **Execution Governor（执行治理器）**，对高风险 Skill 请求进行核验和授权。

| 组件 | 可信假设 | 不能默认成立的假设 |
|---|---|---|
| Trusted Evidence Hub | 核心代码、可信规则、访问控制与记录完整性不被攻击者修改 | 输入的环境事实全部真实 |
| Planner / Cognition | 可生成候选 Task Plan、Skill 调用 | 其计划或自我安全判断一定正确 |
| 环境输入与 World State | 可提供待核验的动态事实 | 感知、摘要、外部文本与执行反馈不会被污染 |
| Execution Governor | 作为可信执行准入点，不允许未授权绕过 | 单独依赖 Planner 声明就能确认物理安全 |

- **TEE 是可选实现手段**：只有当威胁模型需要抵御宿主系统对 Hub 或 Governor 的篡改时才考虑；也可以先采用权限隔离、受保护状态服务和可追溯记录。
- **根本区别：Hub 可信 ≠ Hub 中的所有事实真实。** 否则环境状态污染攻击已被研究假设直接排除，检测问题会退化。
- **已有近邻：** KnowRob、MoveIt Planning Scene Monitor、Governed Shared Memory、Traceable World State、Runtime Governance for Embodied Agents、ROS2 Security Enclaves 与 TEE/远程证明工作。**共享知识/状态管理、统一准入或 TEE 本身不是核心创新**。

## 四、候选系统架构：四个模块

| 模块 | 主要功能 |
|---|---|
| **1. Trusted Goal / Policy** | 保存可信用户授权目标、安全规则和可执行权限；防止环境文本伪装成高级指令。 |
| **2. Plan-to-Evidence Mapping** | 从候选 Plan / Skill 中提取安全关键动作及前置条件，并关联支持这些条件的环境事实。 |
| **3. Evidence Trust / Conflict Monitor** | 利用 Hub 检查证据来源、完整性、时效性、相互依赖、冲突与缺失；不将多个共享同一错误来源的判断误认成独立证明。 |
| **4. Selective Verification / Intervention** | 按动作风险和证据充分性决定 Allow、Re-verify、Block 或 Replan，并控制监控成本与响应时限。 |

**工作流程：**

```text
Trusted Goal / Policy          Potentially Untrusted Environment Evidence
            \                            /
             \                          /
              Trusted Evidence Hub (来源、版本、规则、状态)
                               |
                      Cognition / Planner
                               |
                    Candidate Plan / Skill
                               |
                      Runtime Evidence Verifier
                 (前置条件 → 证据依赖 → 可信性判断)
                               |
                   Allow / Re-verify / Block
                               |
                  Robot Skills → ROS → Physical World
```

**安全前提：** 对于来源无法独立核验的高风险事实，监控器不能虚构确定性；应显式报告“证据不足”，采取安全暂停、重新感知或请求额外授权等响应。

## 五、与 CPScope / AgentSight 的结合

- **CPScope：** 借鉴异构双分支、时序行为分析、有界证据保留与风险驱动的监控成本控制。候选迁移方向为 **Planning / Evidence Monitor + Host / Execution Provenance Monitor**；不直接照搬原 Sensor–Gateway–Controller 特征、VAE 或秒级 RC-RBAW。
- **AgentSight：** 借鉴高层 Agent 语义与进程谱系、syscall 的关联机制；第二阶段探索 `Trusted Goal → Plan → Skill → ROS → Process/Syscall → Physical Feedback` 的跨层执行证据链。
- **阶段安排：** 第一阶段专注认知/规划层证据核验与执行前安全准入；第二阶段加入 ROS、系统调用和物理反馈，研究未授权执行与反馈欺骗；自适应窗口/风险驱动核验作为性能优化。
- **潜在创新：** 攻击者存在时的**关键证据可信性判断、独立核验与低开销执行前防御**，而不是 Hub、TEE、双分支或 syscall tracing 本身。

## 六、Benchmark / Dataset / 实验平台

建议采用**一个主闭环仿真平台 + 多种攻击及安全评测数据**，避免一次性部署过多机器人框架。

| Benchmark / Dataset | 主要内容与用途 | 优先级 |
|---|---|---|
| [ESTI / ESTI-Bench](https://arxiv.org/abs/2608.16806) | 环境状态文本污染、恶意计划生成及执行传播；直接对应 A、B 场景 | **S：主要攻击依据** |
| [HarmPlan / PROTEA](https://protea-secure.github.io/PROTEA/) | 正常计划与隐藏恶意步骤，适合测试 Planning Security Judge | **S：Plan 安全对照** |
| [SafeAgentBench](https://safeagentbench.github.io/) | 高层具身任务和危险行为测试；可用于评价正常执行与安全效用 | **S：安全任务评价** |
| [AGENTSAFE](https://openaccess.thecvf.com/content/CVPR2026/html/Ying_AGENTSAFE_Benchmarking_the_Safety_of_Embodied_Agents_on_Hazardous_Instructions_CVPR_2026_paper.html) | 将安全问题按 Perception、Planning、Execution 分阶段评估 | A：阶段性分析 |
| [RoboJailBench](https://purseclab.github.io/benchmark-for-robotics-security/) | 恶意/正常意图配对及攻击—防御比较 | A：安全与正常任务权衡 |
| [SHAWSHANK](https://arxiv.org/abs/2511.16347) | 环境中的间接恶意指令；补充感知—认知边界攻击 | A：攻击泛化 |

**平台建议：** 第一阶段优先 **AI2-THOR / SafeAgentEnv** 做真实任务状态驱动的闭环验证，辅以 **VirtualHome + HarmPlan** 做低成本计划级试验；第二阶段迁移到 **ROS2 + Gazebo** 或机器人实机。

**数据缺口：** 以上公开 benchmark 不一定提供 `True World State / Attacker-Controlled State / Evidence Source / Independent Verification / Execution Outcome` 的完整对应标签。因此需要构建适量受控场景及可信证据元数据。仿真器 Ground Truth **仅用于评价**，不能直接泄露给监控模型。

## 七、Baseline

| 对比类别 | 代表方法 | 目的 |
|---|---|---|
| **无防御与普通一致性** | No Defense、Goal–Plan Consistency、Plan–Action Consistency | 判断普通一致性是否已足够检测攻击 |
| **具身规划与安全防御** | [PROTEA](https://protea-secure.github.io/PROTEA/)、[RoboGuard](https://arxiv.org/abs/2503.07885)、[PerceptTwin](https://arxiv.org/abs/2606.04226) | 比较恶意计划审查、独立约束、场景验证的效果 |
| **Agent 来源与权限控制** | [CaMeL](https://arxiv.org/abs/2503.18813)、[PACT](https://arxiv.org/abs/2605.11039) | 判断通用信息流、来源及参数级权限约束能否解决具身状态污染 |
| **组件消融** | 无可信 Hub、无来源/依赖信息、无独立核验、无选择性核验、完整系统 | 证明每个模块的必要性 |
| **系统扩展对照** | AgentSight、CPScope、ROS tracing | 第二阶段比较跨层执行可见性及系统开销 |

**对比注意事项：** CaMeL、PACT、PerceptTwin 等不一定能在同一机器人环境直接运行；如果适配，要注明保留和简化的机制，不能将弱化版称为原论文完整实现。

## 八、Metric

| 维度 | 指标 | 评价目标 |
|---|---|---|
| **攻击效果** | Planning ASR、Execution ASR | 区分恶意计划生成与真实执行后果 |
| **检测质量** | Precision、Recall、FPR、F1 | 判断检测能力和误报 |
| **实际防御** | Attack Prevention Rate、Unsafe Action Rate | 是否在危险动作执行前阻止攻击 |
| **正常任务能力** | Benign Task Success Rate、False Block Rate | 避免以拒绝所有任务换取低 ASR |
| **证据判断** | Evidence Attribution Accuracy、Conflict Detection Recall、Evidence Sufficiency Accuracy | 是否识别关键污染来源、证据冲突和不足 |
| **运行时代价** | Detection / Verification Latency、p95/p99、模型调用次数、CPU/内存 | 监控是否可部署并满足执行时限 |
| **选择性核验** | Verification Rate、Unnecessary Verification Rate、Recovery Success Rate | 衡量核验策略、任务恢复和安全—成本权衡 |

**最关键的四项：** **Execution ASR、Benign Task Success Rate、False Block Rate、Verification Latency**。

## 九、实验实施安排

1. **阶段一：确认问题**——复现 ESTI 等状态污染攻击，评估 Goal–Plan / Plan–Action Consistency、PROTEA、RoboGuard 等是否因共享错误证据出现系统性漏报；分析漏报原因。
2. **阶段二：最小原型**——实现可信 Hub、前置条件提取、证据核验和执行准入；先采用规则与现有 LLM/VLM，验证核心防御收益。
3. **阶段三：模型与优化**——研究安全关键证据依赖、冲突识别、按风险选择核验，以及模型/验证器调用开销；开展对照与消融。
4. **阶段四：系统扩展**——接入 ROS2、AgentSight/CPScope 风格系统证据，验证执行反馈伪造、未授权执行及相关系统开销。

**关键 Go / No-Go 条件：** 必须找到至少一组可复现攻击，使现有规划验证或一致性方法因共享污染状态漏报，而引入真实独立证据后能降低实际执行级攻击成功率，同时不显著破坏正常任务能力。若简单的可信状态查询已经充分解决问题，则需要重新审视方法创新点。

## 十、组会总结：Research Insight

**现有具身安全监控通常关注计划是否符合目标、安全规则或生成动作，但这些判断依赖的环境事实本身可能被攻击者污染。** 当 Planner 与 Safety Monitor 共享同一份错误环境证据时，多模型审核和一致性验证可能同时失效。我们考虑通过逻辑上可信的证据管理中心与独立执行准入，追踪安全关键动作依赖的事实、核验来源与独立性、在证据冲突或不足时进行选择性补充验证，并在物理执行前阻止高风险行为。**可信资源池只是系统基础，真正的候选创新是主动攻击下更可靠的证据充分性判断和低开销在线防御。** 该方向已有强相关工作（RoboGuard、PerceptTwin、PROTEA、CaMeL、PACT、AgentSight 等），因此不能宣称相关概念首次提出；必须通过明确攻击模型及严格 baseline 验证其方法层面的新颖性。

## 主要参考论文与链接

- [ESTI: Environment State-Text Injection Attack](https://arxiv.org/abs/2608.16806)
- [PROTEA / HarmPlan](https://protea-secure.github.io/PROTEA/)
- [RoboGuard](https://arxiv.org/abs/2503.07885)
- [PerceptTwin](https://arxiv.org/abs/2606.04226)
- [RoboSafe](https://arxiv.org/abs/2512.21220)
- [CaMeL](https://arxiv.org/abs/2503.18813)
- [PACT](https://arxiv.org/abs/2605.11039)
- [AgentSight](https://arxiv.org/abs/2508.02736)
- [Runtime Governance for Embodied Agents](https://arxiv.org/abs/2604.07833)
- [Traceable World State](https://arxiv.org/abs/2610.12033)
- [No Free Checker](https://arxiv.org/abs/2609.09250)
- [CPScope：用户提供的 Fanhang_NDSS(2) 研究稿](https://www.ndss-symposium.org/)（仅列研究背景；本链接是会议主页，并非该稿论文链接）

> **说明：** 本文是研究构想与实验计划，并非已实现系统或已经证明的研究贡献。公开 benchmark 是否含有所需证据标签、各基线能否复现及是否存在共同漏报，均需在正式实验前核验。
