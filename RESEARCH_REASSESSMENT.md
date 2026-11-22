# 研究与实验方案复评（2026-10-22）

## 判断

**场景可行，适合继续做有明确威胁边界的安全评估。当前证据支持条件性的错误授权机制，尚不足以证明九个官方系统被攻破，或必须提出复杂新防御。** Proposal-3 与 exp-5 把下一阶段重心放在入口、因果归因和强简单防御上，这个调整合理。

本次依据是完整的 `share-pool/exp-5.md`、`Proposal-3.md`、E1/E2 报告、CSV 及 XLSX 五张表、实验代码的入口/导入/路径/结果写入审计和关键原生模块；同时重新访问了下列论文与官方资源。这里的结论是评估与整理，不代表执行了 E4–E6，也没有重跑远程模型或危险模拟动作。

## 1. 科学问题怎样才不是重复已有工作

形式化 Monitor 验证的是“输入状态和动作所描述的命题是否满足规则”。输入事实失真时，逻辑正确并不推出物理安全。RoboGuard 原论文 §V 已明确将准确世界模型列为前提，并承认严重受损的世界模型会导致安全失败。因此，仅演示“假状态使规则误判”难以单独构成新的研究贡献。[RoboGuard 原文 §V](https://arxiv.org/html/2503.07885v2)

ESTI 已把对象属性、关系、动作条件和反馈作为状态文本攻击面，并考察规划到执行的传播。可区分的研究切口应是：**在冻结安全政策、证据权限和动作可执行性的条件下，测量执行前授权如何继承错误事实，哪些独立核验能修复，以及修复的安全、任务效用和成本。** 这属于基于两项工作的研究定位推断，不能宣称状态污染攻击本身首次提出。[ESTI v3](https://arxiv.org/html/2608.16806v3)

“共享”需要真实数据链证明。固定同一危险动作时，Monitor-only 与 Shared 若给 Monitor 相同输入，得到相同 ALLOW 本来就是预期；它不能独自证明 Planner 与 Monitor 的独有联动效应。完整链需要同时观察：污染改变 Planner 的提议；对应危险提议到达安全门；安全门基于错误事实放行；Executor 的原生动作成功且违反预先定义的政策。

还要区分三个问题：事实真实性、动作轨迹完整性、检查—使用时间一致性。Refinement Gap 研究高层动作到执行轨迹的信息遗漏；TOCTOU 研究检查后状态改变。它们可以共存，但不是同一污染机制，不能将同一条结果重复计为三种攻击成功。[Refinement Gap](https://arxiv.org/html/2610.02662v1)

## 2. 现有证据的实际强度

| 证据 | 能支持什么 | 目前的边界 |
|---|---|---|
| E1 微波炉属性 | 固定危险动作发生错误 ALLOW | 原生 `OpenObject` 拒绝通电开门，执行成功不成立 |
| E1 含卡微波炉通电 | 受控错误授权后，原生 Toggle 成功违反研究者合约 | 固定动作、测试副本、非完整 LLM Planner；不模拟真实火灾 |
| M5/M6 厨房规则 | 原生 `empty_burner_toggle` 依赖父容器/位置等输入；同源几何自洽不充分 | 包装器、替代观察与 Planner 代理不等于已证实低权限生产者攻击 |
| b1 / b9 | 原组件上的语义目标别名和模型规划可影响授权 | 共用 SPINE/RoboGuard 与单地图；无真实 ROS 发布者权限/导航；简单几何有效 |
| b2 / b3 | Z3 合同、历史及多分支一致性也可能继承假事实 | 研究者机制实现，不是官方 SafeGate/RoboSafe |
| b4 / b7 实时融合 | 官方 2B 模型参与研究者前置门，单例危险与安全 Unity 动作均实际执行 | Planner 未参与；融合门/锅具政策新增；EMBGuard 不读结构化共享状态；有 forceAction 条件 |
| b5 | 共享视觉缺失可能影响异步告警，且简单质量门有效 | 告警不是前执行授权；黑帧不是内部一致的语义假事实 |
| b6 / b8 | 官方符号/软件权限组件可配受控事实做补充分析 | SELP 不完整端到端；GuardAgent 不属于具身核心直接对比 |

关键本地复核结果：b4 的 20 条原始预测与 Parquet ID、Action、标签和图像 SHA 一致，仍为 TP8/FN2/TN4/FP6；5 对同图异动作仍整对正确 0/5。b9 汇总仍为 8 任务、16 调用、危险严格配对 3/4、安全 6/6，简单防御将误授 3→0。这些是已有数据的一致性复核，不是本次新增模型实验。

最有力的反例必须保留：b7 同 Unity fresh metadata 在危险组最终 DENY、良性组 ALLOW；b9 图内位置冲突检查化解当前别名攻击；E2 提交前重查挡住受控竞态。它们不会否定条件性风险，但会限制“简单防御不足”和新 Design 的主张。

目录中还已有 `results/E4/00_inventory/` 的六个候选任务/资源审计文件：四组 SafeAgentBench 配对的静态命令规则检查，以及 FloorPlan3/403 的真实对象发现。它们未做状态污染或危险动作，部分危险任务的静态 ALLOW 也不是被污染后绕过 Monitor 的证据；不能当作 exp-5 所要求的入口、配对执行和泛化验收已完成。本次原样保留这些早期 E4 记录。

## 3. 代码层面看到的真实依赖

厨房原生读取链是 `controller.last_event.metadata['objects'] → build_kitchen_snapshot → check_toggle_scene_safety`，随后才进入交互执行。源码见 [kitchen_safety.py](external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py) 与 [controller.py](external/safe-hierarchical-embodied-ai/src/ae_rl/rl/interaction/controller.py)。测试中可替换观察或 patch 快照，不代表实际部署已有不可信网络生产者进入该链。

SPINE 确有 `input_graph_cbk`，但启动时全图加载与运行时增量更新的能力不同。已记录 J/K 表明运行时可追加别名，却不能据省略消息删除旧节点或覆盖其坐标；启动图替换又是另一权限。该接口存在、模拟调用成功和真实敌手有权限发布消息，是三个不同证据层次。

PerceptTwin 的 Unity 技能与后审计应放在数字孪生验证语境：仿真中先执行再 Judge，并不自动意味着物理机器人也先危险执行再防护。新增前置 StateMonitor 的授权结论要单独报告。其论文原本就是用重建仿真反馈改进机器人执行前的计划验证。[PerceptTwin](https://arxiv.org/abs/2606.04226)

当前代码与历史实验记录存在模型配置差异：部分 PerceptTwin/融合源码默认 `deepseek-v4-pro`，表格与部分旧日志写 `deepseek-flash`。本次保留源码默认值、原日志与两者区别，不凭新源码反写旧结果。未来每次运行需保存请求模型名、响应模型名、参数、Prompt 和代码 SHA。

## 4. 对 exp-5 的建议

继续按 E4-0 → 最小有效配对 → E5 来源/目标归因 → E6 统计顺序推进，本次不启动这些新实验。优先补齐以下证据：

1. **真实入口和权限。** 冻结攻击者、可改字段、生产者及两个消费者的实际读取路径。找不到低权限入口时继续明确 T0，不把进程分离或 Unity 真执行自动视为 T1/T2。
2. **两个可执行事实族与固定政策。** 厨房关系与对象属性可先做；每个目标都有真实安全/危险正反例。无锅不开火是研究者政策时，对所有被比较配置事前明确提供，同动作/同规则比较。
3. **解耦 Planner 和 Monitor。** 同一状态配对分别测 Clean、Planner-only、Monitor-only、Shared、Placebo；固定候选的 `UAR_probe` 与真实 Planner 的危险提议率单列。
4. **先排除强简单修复。** 同源重复、可得的受保护新鲜查询、目标绑定、UNKNOWN/DEFER、必要时版本/序列化，使用相同证据预算；拿不到真实部署证据的 metadata 条件标 X 上界。
5. **冻结分母与样本簇。** 同一物理状态的所有条件放在同一 split；报告所有尝试、无计划、无效输出、接口不支持和执行失败。多次 seed 与重复模型调用不自动变成独立场景。

指标还应同时保留端到端事件比例及条件比例。例如 `P(unsafe proposal)`、`P(ALLOW | unsafe proposal)` 与完整有效攻击回合中的执行违规率分别回答不同问题；仅报告条件 UAR 会隐藏 Planner 根本没生成危险动作的回合。`forceAction` 的场景构造和最终危险动作分别标注，不能只用一个布尔量混过去。

EMBGuard 的原生观测—动作风险与私有炉灶合同并不等同；V0 原格式与 V1 固定政策适配分开符合其官方接口定位。额外 RGB 只有在对应目标、时刻和政策所需事实可辨时才提供有效新信息。[EMBGuard](https://proceedings.mlr.press/v306/choi26i.html)

若所有被测安全和危险世界对防御呈现完全相同的证据，防御无法凭重复推理确定哪一个是真实世界。这是对信息条件的推论；合理安全策略可以 DEFER，但必须计算恢复成本和正常任务损失。来源可追踪和传输完整也不等于物理语义真实，不能用 provenance 日志替代事实核验。

## 5. 文字材料中的口径问题

- exp-5 §1–§6 已注明是历史设计；实际状态优先读 §0、§7–§14、XLSX 最新追加行及原始 JSON。CSV 后半段仍有 HD-Guard“待执行”、b9“下一步启动”的旧文字，不能拿这些旧行推翻新结果。
- 早期 E1/E2 的 T0/T1/T2 是 Clean/Planner-only/Shared **条件**；Proposal-3 的 T0/T1/T2 是 controlled-copy/producer-output/end-to-end **能力**。后续日志建议分别用 `condition` 与 `attacker_level`，旧数据不改值。
- O 应限定到实际运行的组件/接口。官方权重加载成功不等于完整官方机器人系统；A/M/U/X 和 N/K/H/软件轨道继续分开。
- C1 已有基础，C2 仍待入口、跨事实/场景与同预算比较；C3 必须由简单防御后的剩余问题触发。若简单核验足够，系统化测量与负结果仍是诚实产出。

## 6. 本次重新访问的文献与资源

以下是本次在线核对的主题和作用，非逐篇完整复现实验。未确认官方完整代码的项目只记录“本次未确认”，不推断永久不可用。论文/官网访问成功也不等于本机资源齐备。

| 文献/资源 | 本次核对后用于本研究的定位 |
|---|---|
| [SayCan](https://arxiv.org/abs/2204.01691)、[ProgPrompt](https://arxiv.org/abs/2209.11302)、[VoxPoser](https://arxiv.org/abs/2307.05973) | 语言规划与技能/环境 grounding 的背景；不是同构的运行时 Monitor |
| [AI2-THOR](https://arxiv.org/abs/1712.05474)、[SafeAgentBench](https://safeagentbench.github.io/) | 交互环境与安全任务资源，不能把任务执行能力当防御失效 |
| [RoboGuard](https://arxiv.org/abs/2503.07885)、[官方代码](https://github.com/KumarRobotics/RoboGuard)、[SPINE](https://arxiv.org/abs/2410.03035)、[代码](https://github.com/KumarRobotics/SPINE) | 语义图、LTL、真实规划接口；准确世界模型假设和原模型差异必须明示 |
| [SafeGate](https://arxiv.org/html/2604.05427v1) | 不只有 Z3，还包括 Hazard Binding、unknown/deferral 与运行期合同；本次未确认完整官方代码，本地仍标 inspired |
| [RoboSafe](https://arxiv.org/html/2512.21220v2) | 当前观察、动作与任务输入，双向推理和长短记忆；不能删除原视觉/记忆后称官方失效，本次未确认完整官方仓库 |
| [DoReMi](https://arxiv.org/abs/2307.00329)、[VeriGraph](https://arxiv.org/abs/2411.10446) | 执行偏差恢复与图式计划核验已被研究；二次检查本身不是创新 |
| [EMBGuard 论文](https://proceedings.mlr.press/v306/choi26i.html)、[代码](https://github.com/dongwxxkchoi/EMBGuard)、[2B 权重](https://huggingface.co/EMBGuard/EMBGuard-2B) | 观测—动作风险分支；本地用固定版本 v1 数据，不能混成网站新版本成绩 |
| [HomeSafe-Bench / HD-Guard](https://arxiv.org/abs/2603.11975)、[代码](https://github.com/pujiayue/HomeSafe-Bench) | 流式异步危险检测；告警/视频事件评分与前执行授权分开 |
| [SELP](https://arxiv.org/abs/2409.19471)、[官方仓库](https://github.com/lt-asset/selp) | LTL 等价投票、受约束解码、领域微调；本地完整生成资源仍未齐备 |
| [PerceptTwin](https://arxiv.org/abs/2606.04226)、[代码](https://github.com/Velythyl/PerceptTwin) | 感知场景重建、仿真验证与反馈；本地新增锅具门不冒充官方政策 |
| [GuardAgent](https://proceedings.mlr.press/v267/xiang25a.html)、[项目](https://guardagent.github.io/) | 官方评估为医疗访问/网页权限，保留软件 Agent 补充，不强行归为具身同类 |
| [Mind the Refinement Gap](https://arxiv.org/abs/2610.02662) | 高层—细化轨迹差异；本次未确认独立完整仓库，本地为 paper-guided 组件评估 |
| [CORE](https://arxiv.org/abs/2602.19983)、[SPARQ](https://arxiv.org/abs/2409.17630)、[Risk-Aware Grounding](https://arxiv.org/abs/2609.37554)、[PROTEA/HarmPlan](https://protea-secure.github.io/PROTEA/) | 分别涉及上下文视觉约束、感知失败恢复、grounding 风险与计划 Judge；适用动作和证据权限需逐项对应 |
| [ESTI](https://arxiv.org/abs/2608.16806)、[Typographic Attacks](https://arxiv.org/abs/2605.18593)、[Seeing is Not Believing](https://arxiv.org/abs/2609.08280) | 既有状态/感知/消息发布前攻击路径；不等于本地已经实现同样权限 |
| [Traceable World State](https://arxiv.org/abs/2610.12033)、[CaMeL](https://arxiv.org/abs/2503.18813)、[PACT](https://arxiv.org/abs/2605.11039) | provenance/replay、控制流隔离、参数来源策略；事实真实性应与权限完整性区分 |
| [具身安全综述](https://arxiv.org/abs/2608.16843) | 以首次受损信任边界组织威胁，为分类提供背景，不能据此宣称空白研究领域 |
| [AGENTSAFE](https://openaccess.thecvf.com/content/CVPR2026/html/Ying_AGENTSAFE_Benchmarking_the_Safety_of_Embodied_Agents_on_Hazardous_Instructions_CVPR_2026_paper.html)、[RoboJailBench](https://purseclab.github.io/benchmark-for-robotics-security/) | 多阶段安全评估与配对安全/恶意任务资源；CVF 直开曾返回403，已通过官方搜索索引交叉核对，不记作本机数据已下载 |

ESTI 在当前 arXiv v3 的标题是 *Breaking Planner Integrity Boundary: Enviroment State-Text Injection Attack on LLM-Driven Embodied Agents*；Proposal-3 使用的是该 ID 的另一标题写法。未来正式参考文献应固定版本、标题与日期，历史 Proposal 本次未覆盖。[当前记录](https://arxiv.org/abs/2608.16806)

## 7. 本轮范围与交付

已整理代码、环境与证据索引，并对现有结果做离线一致性验证。没有启动 E4/E5/E6、修改安全政策、切换模型、安装依赖或重跑大模型。下一阶段值得继续的前提是把“谁能写哪条环境事实、哪些模块实际读取它、什么动作真实执行”变成同一条可审计因果链，而不是继续增加相同炉灶单例或重复九项模型。
