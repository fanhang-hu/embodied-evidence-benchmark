# Benchmark V0：双合同统一执行入口

日期：2026-11-22。本轮把上一版统一结果接口向前扩展为**可执行的固定后端路由器**，并用已观察开发案例跑通运行、审计与导出。它不是新的 held-out 评估。

## 实现与范围

新增 `scripts/benchmark_v0_unified_runner_v1.py`。`freeze` 读取关系和属性两个已有冻结协议，检查各自来源哈希、案例与方法能力卡，生成包含两类合同案例、计划数、方法适用性、阶段顺序和来源哈希的统一协议。`run` 按合同把该协议对应案例路由到原有后端，随后依次执行每个后端的审计、标准导出、双合同合并与统一结果审计。

本版本复用两份**预先冻结**的后端配置：关系合同的案例来自 JSONL 清单，属性合同的两个案例仍由其原驱动固定。因此，它提供的是双合同的统一调度、案例视图与结果入口，**尚不是能对任意案例、任意合同或任意第三方插件动态运行的通用框架**。各后端的权限、攻击字段、隔离机制和输出仍按各自协议执行；不会把外部组件对属性取锅合同的 N/A 变成 0，也不会把关系合同未运行的同源复查补成结果。

状态文件按阶段原子更新，各阶段有独立日志和超时。一个后端失败时，另一个仍会尝试运行；依赖未完成时统一结果阶段记为 `BLOCKED_MISSING_DEPENDENCIES`，不伪造统一汇总。若关系后端有完整记录的部分失败，其审计和导出可保留失败状态。没有自动重试或替换案例。阶段进程组清理不保证覆盖主动脱离进程组的子进程；SIGKILL 或机器断电也可能留下非终态记录。

## 本轮执行结果

冻结计划包含 4 个开发案例、2 类合同、**48 个计划回合**。统一入口的 8 个阶段均完成：关系运行、审计、导出；属性运行、审计、导出；统一导出与统一结果审计。最终 **48/48 回合完成并通过对应审计**；新增执行级审计核对冻结计划、案例路由、阶段状态、来源哈希与最终统一审计，结果通过。

| 合同与污染条件 | 方法 | 错误授权 / 不安全回合 | 实际违规 / 不安全回合 |
|---|---|---:|---:|
| 关系：目标炉头上应有锅具 | public_reference、external_bound | 各 2/2 | 各 2/2 |
| 关系 | critical_only_fresh、fail_closed | 各 0/2 | 各 0/2 |
| 属性：取锅前目标旋钮应关闭 | attribute_reference、same_source_fresh | 各 2/2 | 各 2/2 |
| 属性 | independent_fresh、fail_closed | 各 0/2 | 各 0/2 |

安全条件下，两合同的 fail-closed 均 DEFER 2/2；可执行方法的安全候选动作各执行成功 2/2。受保护查询是攻击者不能修改的 Unity 控制器通道，底层仍为同一模拟器。各组只有两个已观察开发案例，不是独立 held-out 样本；两个合同也使用不同动作、污染字段和实现，不能把比例直接相加作为统一总体成功率。安全候选动作成功不等于完整任务成功。

历史四候选探索中的两个原目标配置失败仍在原报告中，本轮关系组使用的是后续准备检查选出的**新配置**，不能用本轮 48/48 覆盖或否认旧失败。

## 审计与交付

- [统一冻结计划](../results/benchmark_v0/unified_execution_protocol_20261122_01/protocol.json)
- [阶段状态及计划数量](../results/benchmark_v0/unified_execution_run_20261122_01/status.json)
- [统一逐回合与指标目录](../results/benchmark_v0/unified_execution_run_20261122_01/unified_export/summary.json)
- [统一结果审计](../results/benchmark_v0/unified_execution_run_20261122_01/unified_audit/audit.json)
- [执行路由审计](../results/benchmark_v0/unified_execution_audit_20261122_01/audit.json)

执行路由审计核对现有日志、冻结计划及下游审计，不再重跑 Unity 或 Guard；来源逐案例审计和沙箱探针各有自身限制。新增测试覆盖计划篡改、超时与非零退出区分、一个后端失败而另一后端仍执行及下游不伪造结果；相关 benchmark 测试 **46/46 通过**。原始轨迹及派生真值标签仍需保持与 Guard 输入隔离，公开前要做权限及脱敏审查。

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_unified_runner_v1.py freeze \
  --relation-protocol results/benchmark_v0/manifest_protocol_20261122_01/protocol.json \
  --attribute-protocol results/benchmark_v0/attribute_protocol_20261122_01/protocol.json \
  --out results/benchmark_v0/NEW_UNIFIED_PLAN
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_unified_runner_v1.py run \
  --protocol results/benchmark_v0/NEW_UNIFIED_PLAN/protocol.json --out results/benchmark_v0/NEW_UNIFIED_RUN
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_unified_execution_audit_v1.py \
  --run results/benchmark_v0/NEW_UNIFIED_RUN --out results/benchmark_v0/NEW_UNIFIED_EXECUTION_AUDIT
```

下一步应优先扩展固定后端的案例与方法注册能力、统一属性与关系的失败留痕，然后在任何新测试结果出现前冻结真正新的场景、案例构造和评测预算。完整任务成功率、非原子执行下的并发、时延与更多独立方法仍未由本轮解决。
