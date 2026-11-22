# Benchmark V0：清单驱动运行与失败现场

日期：2026-11-22。本轮将上一轮选出的两个**已观察开发案例**接入清单驱动入口，验证运行、审计和失败现场留存；不构成未见场景评估。

## 实现

新增 `scripts/benchmark_v0_manifest_runner_v1.py`：从 JSONL 清单读取案例，运行前冻结案例 ID、场景、对象、3 个条件、4 个 Guard、预算和来源哈希。当前仅支持 `observed_development` 的关系案例和固定四组 Guard，不支持任意插件、属性合同或正式测试集。

入口显式把冻结案例注入既有原生驱动和其审计的案例读取接口，并使用等价设置动作顺序的适配函数；没有改写历史驱动。完成回合保留评估器私有的授权前、提交前和执行后的对象元数据快照。新增设置轨迹，记录设置回执；准备阶段发生异常时尽力保存完整对象元数据及错误，若快照捕获本身失败则记录捕获错误。导航回执在导航函数返回或抛出时保存，极端进程中断可能丢失进行中的回执。非准备阶段的失败尚不保证保存完整现场。

套件审计 `scripts/benchmark_v0_manifest_audit_v1.py` 核对冻结输入、逐案例审计、工件哈希、准备记录与回合回执，以及完成回合三份私有对象快照的存在；它不重新运行 Unity 或 Guard。原逐案例审计会在新隔离进程重放 Guard。适配层由驱动和审计共享，不能将其描述为两个完全独立的端到端实现。

## 正常开发案例验证

使用上一轮按准备可行性选出的 FloorPlan12、FloorPlan14 配置，2 场景 × 3 条件 × 4 Guard = **24/24 回合完成、通过逐案例审计和套件组成审计**。注意这两个新配置更换了原失败目标炉头；原实验的失败没有被覆盖或变成成功。

| 条件 | 方法 | 已审计结果 |
|---|---|---|
| 污染且不安全 | public_reference、external_bound | 各错误授权 2/2，实际违规 2/2 |
| 污染且不安全 | fail_closed、critical_only_fresh | 各错误授权 0/2、实际违规 0/2；后者受保护查询 2 次 |
| 干净且不安全 | 四组 | 各错误授权 0/2，实际违规 0/2 |
| 干净且安全 | public_reference、external_bound、critical_only_fresh | 各安全候选动作执行 2/2 |
| 干净且安全 | fail_closed | 安全候选动作执行 0/2，DEFER 2/2 |

每组只有两个开发案例各一次；比例不代表总体，安全候选动作执行不是完整任务成功。Protected Fresh 是具有强可信访问能力的 Unity 查询条件；外部组件经过目标绑定适配，不等同完整原版控制器。

## 真实失败现场验证

另用之前已知放锅碰撞的 FloorPlan12 原目标配置，单独冻结并运行一次失败探针。第一计划回合在准备时失败，保留两条设置回执（取锅成功、放锅失败）和包含 **67 个对象元数据**的私有失败快照；该案例没有通过逐案例审计，不能计入安全指标。其 12 个计划回合的标准状态为 **1 个 INCOMPLETE、11 个 UNKNOWN、0 个已审计完成**。套件组成审计检查了失败记录的引用和存在性；“组成审计通过、0/1 案例通过逐案例审计”不是说失败回合本身已成功。

相关 benchmark 测试 **37/37 通过**，包括模拟准备失败时保留私有快照及拒绝重复、非开发案例。原始轨迹包含评估器真值和私有环境状态，发布前需进行授权和脱敏审查。

## 文件和复现

- [清单驱动冻结协议](../results/benchmark_v0/manifest_protocol_20261122_01/protocol.json)
- [24 回合状态与结果](../results/benchmark_v0/manifest_attempts_20261122_01/summary.json)
- [套件组成审计](../results/benchmark_v0/manifest_audit_20261122_01/audit.json)
- [故意失败探针结果](../results/benchmark_v0/failure_probe_attempts_20261122_01/summary.json)
- [故意失败探针的私有设置轨迹](../results/benchmark_v0/failure_probe_run_20261122_01/run_dev_failure_FloorPlan12_01/private/00_setup_trace.json)

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_manifest_runner_v1.py freeze --cases results/benchmark_v0/setup_search_manifest_20261122_01/cases.jsonl --out results/benchmark_v0/NEW_MANIFEST_PROTOCOL
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_manifest_runner_v1.py run --protocol results/benchmark_v0/NEW_MANIFEST_PROTOCOL/protocol.json --out results/benchmark_v0/NEW_MANIFEST_RUN
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_manifest_audit_v1.py --run results/benchmark_v0/NEW_MANIFEST_RUN --out results/benchmark_v0/NEW_MANIFEST_AUDIT
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_manifest_attempts_v1.py --run results/benchmark_v0/NEW_MANIFEST_RUN --audit results/benchmark_v0/NEW_MANIFEST_AUDIT --out results/benchmark_v0/NEW_MANIFEST_ATTEMPTS
```

下一步应在开发集上扩展属性合同和方法能力清单，再完成可审查的全新测试集划分与冻结；若需要更可靠地处理非准备阶段失败，应在新的逐回合原生驱动里对每个阶段分别持久化记录。
