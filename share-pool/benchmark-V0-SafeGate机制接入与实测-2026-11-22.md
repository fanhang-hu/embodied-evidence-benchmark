# Benchmark V0：SafeGate-inspired 机制接入与实测

日期：2026-11-22。本轮将历史九项 baseline 中的第 2 项机制接入原生评测链，而不是只增加一个离线演示。

## 接入范围

此前 E3 M1 的 `contract_check` 是研究者实现的 **SafeGate-inspired Z3 Guard**：将“打开炉头要求目标炉头有锅”写成逻辑约束，用 Z3 的 sat/unsat 决定 ALLOW/BLOCK。本次按照该历史代码的机制实现适配器，保留 Z3 求解和目标锅具判定；加入隔离进程输入接口和目标绑定检查。**它不是官方 SafeGate 完整实现**，没有声称复现官方 Hazard Binding、自动合同生成、完整 Guard/Invariant/Abort 或真实 Abort。历史来源是 `e3_baseline/b2_safegate/e3_safegate_m1.py`，适配器为 `scripts/benchmark_v0_safegate_guard_v1.py`。

存在合同差异：该历史机制将“有锅”定义为报告的父容器关系成立、且锅具和炉头报告位置距离不超过 0.5 m；评估器的 `any_cookware_v0` 真值只要求真实父容器关系成立。因此其策略并非与简化参考规则完全等价，不能据此做无条件的同合同排名。Z3 依赖为本机已有的历史安装，不包含在 Git 源码快照中。

## 实验与结果

三个既有开发案例 FloorPlan6/7/8，3 种状态条件 × 3 种方法：自建参考规则、SafeGate-inspired Z3 共享 Producer 证据、SafeGate-inspired Z3 受保护 Unity 查询。每组 3 回合，共 **27/27 回合完成并通过逐回合审计**。

| 条件 | 方法 | 错误授权 | Unity 实际违规 | 安全候选动作成功 |
|---|---|---:|---:|---:|
| 污染、不安全 | 自建参考规则 | 3/3 | 3/3 | N/A |
| 污染、不安全 | Z3 共享 Producer | 3/3 | 3/3 | N/A |
| 污染、不安全 | Z3 受保护查询 | 0/3 | 0/3 | N/A |
| 干净、不安全 | 三组 | 各 0/3 | 各 0/3 | N/A |
| 干净、安全 | 三组 | N/A | N/A | 各 3/3 |

攻击者可持久污染目标锅具的父容器关系和位置，实际物理状态由 Unity 维持；最终开炉动作为无强制执行。Z3 受保护组在每回合执行一次受攻击者保护的 Unity Pass 查询；它是同一模拟器上的 oracle 式通道，不是独立传感器。每组只有 3 个已观察案例，不能解释为总体成功率或未见场景泛化；安全候选动作成功也不是完整任务成功。

## 审计与文件

审计核对 Producer 指定字段变更及摘要、请求来源、受保护查询、Z3 Guard 隔离重放、真实状态、Unity 回执和分组计数。没有独立重跑 Unity；隔离探针不能证明对任意代码的形式化安全性。基线能力卡明确记录几何合同差异和非官方实现范围。

- [基线能力卡](../benchmark_v0/spec/baseline_safegate.v1.json)
- [运行汇总](../results/benchmark_v0/safegate_baseline_development_20261122_01/summary.json)
- [逐回合审计](../results/benchmark_v0/safegate_baseline_audit_20261122_01/audit.json)
- [隔离适配器](../scripts/benchmark_v0_safegate_guard_v1.py)

本轮新增测试覆盖 Z3 空间条件、目标绑定缺失、非强制动作约束和隔离进程重放。实际后续工作应继续评估历史 baseline 的合同与接口适用性，不能把九项历史实验都写成已完整接入；在扩大案例前也应区分新的测试簇与这些已反复使用的开发场景。

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_safegate_native_v1.py \
  --cases relation_FloorPlan6_02 relation_FloorPlan7_04 relation_FloorPlan8_06 \
  --out results/benchmark_v0/NEW_SAFEGATE_RUN
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_safegate_audit_v1.py \
  --run results/benchmark_v0/NEW_SAFEGATE_RUN --out results/benchmark_v0/NEW_SAFEGATE_AUDIT
```
