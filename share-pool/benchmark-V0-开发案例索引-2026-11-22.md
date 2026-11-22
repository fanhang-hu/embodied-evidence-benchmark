# Benchmark V0：开发案例索引与下一步核验

日期：2026-11-22。状态：**历史案例索引已生成；尚未建立可运行 benchmark。**

| 文件 | 内容 |
|---|---|
| [案例 CSV](../results/benchmark_v0/development_index_20261122_01/cases.csv) | 可查看的 12 条案例配置、目标 ID、合同类型及历史来源 |
| [案例 JSONL](../results/benchmark_v0/development_index_20261122_01/cases.jsonl) | 机器可读的相同配置 |
| [索引 manifest](../results/benchmark_v0/development_index_20261122_01/manifest.json) | 输入哈希、输出哈希、数量、范围和限制 |
| [生成脚本](../scripts/benchmark_v0_inventory_20261122.py) | 仅标准库、无模拟器／模型调用；拒绝覆盖输出 |
| [B0 定位与文献比较](benchmark-B0-定位与相关工作审查-2026-11-22.md) | 候选研究问题、相关工作、威胁模型及适配边界 |

## 范围和来源

索引包含 12 个**案例配置**：E4 已冻结清单 8 项（FloorPlan5–8），E6 在线协议清单 4 项（FloorPlan9–10）；涉及 6 个物理场景、7 个属性合同配置、5 个关系合同配置。同一场景、目标和合同的关联不可忽略。这不是 12 个独立场景、12 个新实验或 12 个测试样本簇。

历史 E4／E6 的小规模 heldout 在各自当时有原定义，但现在已被本项目观察和分析。**12 项在新的 benchmark 开发中均标为 `observed_development`，新增未知测试项为 0。**源 case ID、原历史 split 和可定位的源行／数组位置均保留，不重命名历史记录。

每条只提取场景、目标对象标识、合同事实族、来源及哈希。原 E4 清单包含真值和构造信息，本索引没有复制其 `trials` 快照；实际系统输入与 evaluator 私有数据是否隔离仍需要在每个运行管线中进一步验证，不能因为索引中不包含 `trials` 就视为隔离通过。

由于个别 run 的攻击条件、字段和能力不同，索引没有为某个案例统一赋予攻击权限。**案例配置不等于轨道或条件实验记录**：某个案例出现在源文件中，不能推断所有 Guard、攻击条件和 Planner 都已运行。具体实验应回到各自冻结 protocol 和 run。

## 已经核对与还没有核对的部分

- 脚本检查 E4 源清单 8 条有效项、E6 在线冻结协议 4 条、case ID 唯一性和支持的事实族。
- E6 在线协议 SHA-256 与已归档 E6 验收中的来源哈希匹配；两种源文件和索引产物的哈希记录在 manifest。
- **没有新运行**原生准备、合同真值、字段污染、模型、Guard 或动作执行；没有验证新测试集或外部适配器。
- E4 历史清单取整文件哈希用于追溯；此前 E4 的正式审计结论仍以 [E4 阶段评估](../E4_ASSESSMENT.md) 为准，本索引生成不是其新一轮逐回合审计。

## 后续具体工作

1. 补充每条案例到已有 E4／E5／E6 协议、条件、guard 和轨迹的映射，分别标记在线、归档计划与确定性 Planner；缺的组合保持缺失。
2. 定义分离的公开案例描述、私有 evaluator 真值和逐步运行结果 schema，加入输入投影及哈希验证。
3. 静态审查 E6 固定计划执行入口和一个非自建外部方法的输入／动作／授权接口，给出可接入、不兼容或需适配的证据；然后再确定 V0 的实际执行最小协议。
4. 设计新场景／任务划分时，所有这些已观察配置仅用于开发；新 split 需事前冻结，不能由历史 heldout 更名得到。

## 入口兼容性初审

本节是源码静态审查，没有将外部安全模块接入 benchmark，也没有新执行对照。

**现有 E6 入口。** [runtime_v4.py](../e6_validation/runtime_v4.py) 的 `run_episode(controller, case, assignment, provider, planner_mode)` 接收 Planner provider，内部直接调用自有 `authorize`、`NativeDriver` 与 Producer；没有通用外部 Monitor 插件接口。`critical_only_fresh` 在合同关键动作路由到受保护查询，其他动作路由到 shared。要支持外部 Guard，需要在独立版本中定义候选动作、公开事实、Guard 输出、访问权限和查询记账，不能修改冻结的 E6 驱动来改变历史结果。

**外部候选：safe-hierarchical-embodied-ai 的厨房规则。** [kitchen_safety.py](../external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py) 的 `build_kitchen_snapshot(controller)` 直接读取 `controller.last_event.metadata.objects`，再建立旋钮—炉头映射、炉头物品和危险物缓存；`check_toggle_scene_safety(action, snapshot)` 返回 `(allowed, reason, details)`。因此可以审查在候选动作固定的条件下构建**显式适配的 snapshot 输入**，但输入替换仅能表明受控适配，不能证明外部攻击者可改写原生运行时。

更关键的是合同不能默认等价：该外部规则对目标炉头上的物品和安全锅具进行判断，并在旋钮已开启时有提前放行分支；E6 关系合同要求**特定目标锅**的父容器包含**特定目标炉头**，E6 属性合同则是取锅前旋钮 OFF。它们的对象、动作和政策语义不完全一致，尤其外部开关规则不能直接作为 E6 取锅合同的原版实现。必须先列出规则分歧及目标绑定负对照，再决定另立合同／任务或明确 N/A；不能悄悄改写规则后声称同一原版基线。

外部模块是具备不同代码来源的候选组件，不等于一套已完整复现的官方端到端防御系统。二值返回可以映射到 ALLOW／BLOCK，但不可凭空生成原版 DEFER。E3 的 [SafeGate-inspired](../e3_baseline/b2_safegate/README.md) 是研究者机制实现；即使它可输出三值，也不能计作独立的官方 SafeGate 实现。

复建到新目录（不修改源文件）：

```bash
cd /home/yyn/embodied
python3 -B scripts/benchmark_v0_inventory_20261122.py \
  --output results/benchmark_v0/development_index_NEW
```
