# Benchmark V0：双合同统一结果接口

日期：2026-11-22。本轮整合两份已有审计结果，没有新增 Unity 或模型实验。

## 本轮完成

新增统一能力卡、逐回合字段规范、导出器和结果审计：

- [双合同及方法能力卡](../benchmark_v0/spec/unified_card.v1.json)：记录事实合同、受污染字段、方法实现、证据通道、适用状态和指标分层规则。
- [统一回合 JSON Schema](../benchmark_v0/spec/unified_episode.schema.v1.json)：描述公共字段。导出器另外检查状态与结果的语义一致性；内置检查不是通用 JSON Schema 验证器。
- [统一案例清单](../results/benchmark_v0/unified_export_20261122_01/cases.jsonl)：4 个已观察开发案例。
- [统一逐回合结果](../results/benchmark_v0/unified_export_20261122_01/episodes.jsonl)：48 个计划回合及原始回合哈希。
- [统一指标](../results/benchmark_v0/unified_export_20261122_01/summary.json)：按**合同、条件和原方法名**分组，包含计划数、完成数、各状态、分子、分母、查询与发布计数；零分母为 `null`。
- [统一结果审计](../results/benchmark_v0/unified_audit_20261122_02/audit.json)：通过；逐条核对源导出记录及 24 组指标，检查能力标记、案例映射和来源哈希。审计未重新运行 Unity 或 Guard，依赖两份已有审计及其限制。

统一导出只含被选中的两份来源：关系合同为已完成的 FloorPlan12/14 **新配置**，属性合同为 FloorPlan6/7。两份均为已观察开发实验，各 24 回合完成并通过已有审计，因此统一视图为 **48/48 已审计完成，4 个案例、4 个物理场景**。原本失败的 FloorPlan12/14 旧配置属于另一份探索性实验，没有包含在这 48 个回合内；其失败仍保留在 [四候选场景探索性评估](benchmark-V0-四候选场景探索性评估-2026-11-22.md)，不能将此次结果描述为所有尝试均成功。

## 能力与结果边界

| 方法能力 | 关系合同：目标炉头上有锅具 | 属性合同：取锅前旋钮关闭 |
|---|---|---|
| 自建规则消费 Producer 证据 | `public_reference`，已运行 | `attribute_reference`，已运行；实现及合同不同 |
| 同一 Producer 再查询 | 本次选中的关系套件未运行 | `same_source_fresh`，已运行 |
| 受保护 Unity 查询 | `critical_only_fresh`，已运行 | `independent_fresh`，已运行；同一模拟器的受保护通道 |
| fail-closed | 已运行 | 已运行 |
| 外部厨房组件 | `external_bound`，已适配目标绑定 | N/A：组件不实现取锅合同 |

受污染且真实不安全的两个已完成开发案例中，两合同的自建共享证据规则均各自错误授权并实际违规 **2/2**；受保护查询与 fail-closed 均各自为 **0/2**。属性合同的同源复查为 **2/2**；关系合同没有该组数据。两个合同的动作、可污染字段、方法实现及场景不同，**不能把两组数字直接相加成统一成功率或视为同一种防御的跨合同排名**。每组各 2 个案例且只运行一次，不代表总体概率；安全候选动作执行也不是完整任务成功率。

方法能力卡明确区分 `NOT_RUN` 和 `NOT_APPLICABLE`，两者都没有伪造回合或赋予 0 分。只有经审计的已完成回合进入安全指标分母；计划及其他状态需要同时报告，避免完成案例偏差。导出记录包含评估器真值标签，不能输入被测 Guard；原始轨迹和可公开版本均需另行审查。

## 验证和下一步

新增测试覆盖跨合同能力匹配、未知值和零分母、未运行/不适用不生成伪记录；相关 benchmark 测试 **43/43 通过**。统一接口目前是**结果适配与聚合**，两类合同仍由各自的执行驱动运行，并非已有一个能动态加载所有合同和第三方方法的通用运行器；历史九项 baseline 也未全部接入。

下一步应补齐可配置的合同/方法执行适配，让统一案例清单直接路由到相应驱动，并保留失败和不适用；随后冻结真正新的测试簇，再按一致预算执行。不要将这份开发视图当作正式排行榜。

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_unified_export_v1.py \
  --relation-run results/benchmark_v0/manifest_run_20261122_01 \
  --relation-audit results/benchmark_v0/manifest_audit_20261122_01 \
  --relation-export results/benchmark_v0/manifest_attempts_20261122_01 \
  --attribute-run results/benchmark_v0/attribute_native_20261122_01 \
  --attribute-audit results/benchmark_v0/attribute_audit_20261122_01 \
  --attribute-export results/benchmark_v0/attribute_export_20261122_01 \
  --out results/benchmark_v0/NEW_UNIFIED_EXPORT
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_unified_audit_v2.py \
  --run results/benchmark_v0/NEW_UNIFIED_EXPORT \
  --relation-export results/benchmark_v0/manifest_attempts_20261122_01 \
  --attribute-export results/benchmark_v0/attribute_export_20261122_01 \
  --out results/benchmark_v0/NEW_UNIFIED_AUDIT
```
