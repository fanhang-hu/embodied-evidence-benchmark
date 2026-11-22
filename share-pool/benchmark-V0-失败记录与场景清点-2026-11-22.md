# Benchmark V0：失败记录与场景使用清点

日期：2026-11-22。本轮没有新增 Unity 或模型实验，也没有把任何场景指定为正式测试集。

## 统一记录：计划中的回合都必须可见

新增 `benchmark_v0/spec/attempt.schema.v2.json` 和 `scripts/benchmark_v0_attempts_v2.py`，在旧的逐回合结果格式之外，增加针对计划分配的状态记录：`COMPLETED`、`FAILED`、`INCOMPLETE`、`TIMEOUT`、`UNSUPPORTED`、`NOT_STARTED` 和 `UNKNOWN`。不同状态的含义是记录观察到的运行情况，不应把不适用、未知或超时自动算作防御成功或攻击失败。

当前转换器针对**旧版固定 3×4 套件**，从冻结协议重建全部计划分配，再读取已存在的回合文件。旧驱动只写 `FAILED_OR_INCOMPLETE`，因此转换为 `INCOMPLETE`，不能推断具体失败原因；缺少记录的回合一律为 `UNKNOWN`，不能仅凭文件缺失认定未开始或已失败。格式预留 FAILED、TIMEOUT、UNSUPPORTED 和 NOT_STARTED，但旧驱动并不会产生这些细分状态；今后新驱动需要记录直接证据后才能使用。v2 格式和转换器没有改动历史冻结驱动。

每组汇总同时给出计划数、各状态数和已审计完成数。安全指标目前**只计算通过既有逐案例审计的已完成回合**；这可能产生完成案例偏差，因此必须同时报告各状态数，不能仅报告成功率。分母为零时值为 `null`。未完成回合的真值和结果字段为空；不能用 `false` 充当缺失值。Schema 检查基本结构；转换器还检查状态、字段和执行结果间的语义约束，它不是通用 JSON Schema 验证器。

对已有两场景套件的结果：计划 **24**，完成 **24**，其中逐案例审计通过 **24**，其余状态均为 **0**。v2 的 12 组比率与之前已审计的 v1 导出逐组一致。此结果不表示新格式已在真实的失败、超时或不适用运行上做过端到端验证：本轮用合成部分中断目录验证了 1 条未完成和 23 条未知记录的处理。

- 标准记录：`results/benchmark_v0/attempts_v2_20261122_01/attempts.jsonl`
- 状态和指标汇总：`results/benchmark_v0/attempts_v2_20261122_01/summary.json`
- 测试：benchmark 相关测试 **19/19 通过**，涵盖未知值、未审计回合排除、零分母和合成部分中断等。

导出关联既有审计及原始工件哈希，没有重新运行 Guard 或 Unity。导出目录仍包含 evaluator 标签，不能作为 Guard 输入；公开发布前需另行审查。

## 场景清点：目前没有确定未见测试集

新增 `scripts/benchmark_v0_scene_inventory_v2.py`，核对已有 12 案例索引及历史来源哈希，扫描 `share-pool` 根目录 Markdown，以及 `results/E1`–`E6` 和 `results/benchmark_v0` 中名称匹配 protocol、summary、catalogue 的文件。此次扫描 **179 个文件，跳过 0 个**；原始命中文件和哈希保存在 `results/benchmark_v0/scene_inventory_20261122_02/inventory.json`。

| 范围 | 当前判断 |
|---|---|
| FloorPlan5–10 | 12 条既有案例来自这些场景；全部标为 `observed_development`，各场景有 2 条案例配置。历史名称中的 heldout 不能直接作为新 benchmark 的未见测试集。 |
| FloorPlan1–4 | 在扫描范围内被提及；FloorPlan2–4 也出现在 E4 feasibility 目录的资料中。这里的自动结果只是文本提及，需要进一步检查具体运行记录，不能直接用作未见场景。 |
| 其他场景 | 此次扫描没有发现，并不证明从未被用于其他实验、私人材料或未扫描文件；也不证明可用或符合合同。 |

一次命中不证明发生过实际运行；没有命中不证明独立。该清单用于保守筛查，并非穷尽全部历史文件，也未执行新场景可用性验证。场景级划分还需要考虑共享物体、任务模板及环境布局关联。

## 下一步

1. 新版执行入口在实际触发超时、不支持、失败或中断时写出明确证据和状态，并测试进程意外终止；当前 v2 主要是离线兼容层。
2. 扩展场景来源审计到实际运行日志、任务和布局，选择候选未观察场景；在查看它们的评测结果之前冻结划分、案例生成规则和预算。
3. 再接入第二类合同和更多可比方法，并按数据来源、权限和适用范围分别报告。

复建时使用新目录，不覆盖已有产物：

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attempts_v2.py --protocol results/benchmark_v0/suite_protocol_20261122_01/protocol.json --run results/benchmark_v0/suite_run_20261122_01 --out results/benchmark_v0/NEW_ATTEMPTS
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_scene_inventory_v2.py --out results/benchmark_v0/NEW_SCENE_INVENTORY
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m unittest discover -s tests -p 'test_benchmark_v0*.py' -v
```
