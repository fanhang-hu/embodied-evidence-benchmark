# Benchmark V0：属性合同六场景扩展

日期：2026-11-22。本轮把属性合同扩展到 FloorPlan15–20，执行完整的 Producer 污染、Guard 对照和 Unity 动作；这些是已观察的开发场景，不是正式留出集。

## 设置与案例来源

属性合同 `target_knob_off_v0` 要求目标炉头旋钮关闭才允许取锅。攻击条件下，Unity 中目标旋钮实际开启，受限的自定义 Producer 持续将该旋钮的 `isToggled` 发布为 `False`。候选动作是非强制 `PickupObject`，固定候选动作，没有在线 Planner。

六个锅具、炉头和旋钮配置复用[上一轮关系合同实验](benchmark-V0-关系合同六场景扩展-2026-11-22.md)按物理准备规则选出的配置；它们已经做过关系合同攻击评测，且没有为本轮属性攻击效果筛选，不能称为新发现的独立场景或属性任务专用选择。属性运行器直接尝试这些配置，不在准备失败后替换案例；失败会保留并排除出完成回合分母。

每场景包含三个条件（干净安全、干净不安全、Producer 污染且真实不安全）和四种方法（属性参考规则、同源重新查询、受保护查询、fail-closed），每组各一次，共 6 × 3 × 4 = 72 个计划回合。案例清单见 [attribute_relation_scenes_20261122.jsonl](../benchmark_v0/cases/attribute_relation_scenes_20261122.jsonl)，记录了来源及哈希。

## 结果与分母

**72/72 回合完成并通过逐回合审计**，没有 incomplete 或失败回合。每组分母为 6 个已审计回合：

| 条件 | 方法 | 错误授权 UAR | Unity 实际违规取锅 | 安全候选取锅 | 受保护查询 |
|---|---|---:|---:|---:|---:|
| 污染且真实不安全 | 属性参考规则 | 6/6 | 6/6 | — | 0 |
| 污染且真实不安全 | 同源重新查询 | 6/6 | 6/6 | — | 0 |
| 污染且真实不安全 | 受保护查询 | 0/6 | 0/6 | — | 6 |
| 污染且真实不安全 | fail-closed | 0/6 | 0/6 | — | 0 |
| 干净不安全 | 四种方法分别 | 各 0/6 | 各 0/6 | — | 受保护查询组 6 次 |
| 干净安全 | 属性参考、同源重查、受保护查询 | — | — | 各 6/6 | 受保护查询组 6 次 |
| 干净安全 | fail-closed | — | — | 0/6；DEFER 6/6 | 0 |

攻击组同源重查有 12 次 Producer 发布，即每回合两次；它们仍来自同一受污染的生产者。受保护查询来自 Unity 的受保护通道，是同一模拟器上的 oracle 式对照，而非独立真实传感器。安全候选取锅不等于完整任务成功。

六个场景每组只有一次，不能把 72 条当作 72 个独立场景，也不能据此估计总体成功率。上一轮关系合同也使用这六个场景，因此两个实验可以分别报告，不应视为两批互相独立的场景。外部关系组件不实现此取锅合同，本轮不适用。

## 审计、复现与边界

审计重构每次 Producer 允许改写的字段，核对输入输出摘要、Guard 请求及隔离重放、受保护查询时序、Unity 回执、真假状态和聚合指标；审计不独立重跑 Unity，也不证明隔离对任意程序的形式化安全。单写者实验未保证授权与执行原子化。设置阶段尽可能保留失败快照，其他失败阶段不保证完整现场。本地源码运行仍依赖历史环境和资源，不等于已经打包成可独立安装的 benchmark。

- [逐回合审计](../results/benchmark_v0/attribute_six_scene_audit_20261122_01/audit.json)
- [分组指标与分母](../results/benchmark_v0/attribute_six_scene_export_20261122_01/summary.json)
- [源码快照携带的精简结果](../benchmark_v0/evidence/attribute_expansion_20261122.json)，不能替代原始轨迹
- [属性清单驱动运行器](../scripts/benchmark_v0_attribute_native_v3.py)、[审计器](../scripts/benchmark_v0_attribute_audit_v3.py)、[结果导出器](../scripts/benchmark_v0_attribute_export_v3.py)

以下命令在项目根目录运行，输出目录须是新路径；依次运行仿真、审计和导出。运行器自动记录案例清单和代码摘要，不需要额外手工冻结。

```bash
xvfb-run -a /home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attribute_native_v3.py run \
  --case-manifest benchmark_v0/cases/attribute_relation_scenes_20261122.jsonl \
  --out results/benchmark_v0/NEW_ATTRIBUTE_RUN
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attribute_audit_v3.py \
  --run results/benchmark_v0/NEW_ATTRIBUTE_RUN --out results/benchmark_v0/NEW_ATTRIBUTE_AUDIT
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attribute_export_v3.py \
  --run results/benchmark_v0/NEW_ATTRIBUTE_RUN --audit results/benchmark_v0/NEW_ATTRIBUTE_AUDIT \
  --out results/benchmark_v0/NEW_ATTRIBUTE_EXPORT
```

新增 3 项清单校验测试均通过，覆盖矩阵完整性、错误合同／重复 ID、清单路径范围。本轮首次启动时因旧路径校验不接受案例目录，在创建输出目录和运行任何回合前退出；修正路径校验后完成上述实验。
