# Benchmark V0：属性合同四场景与简化运行

日期：2026-11-22。本轮按用户要求减少重复的协议目录和探针，将属性合同扩展到可选择的既有开发案例，并运行完整条件对照。

## 运行方式

新增 `scripts/benchmark_v0_attribute_native_v2.py`，可通过 `--cases` 指定已有 E4 属性案例，一条命令运行。每次运行目录自动保存本次案例、方法和代码摘要作为结果溯源，**不需要先手工执行独立的 freeze 命令**；这是运行记录，不表示每次开发都需要复制新的冻结目录。未知、重复或关系类案例会被拒绝。本版继续采用隔离的 Producer 和 Guard，设置失败时尽力保存动作回执与私有状态快照。审计和导出使用独立的 v2 脚本，未修改历史版本。

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attribute_native_v2.py run \
  --cases attribute_FloorPlan5_01 attribute_FloorPlan6_03 attribute_FloorPlan7_05 attribute_FloorPlan8_07 \
  --out results/benchmark_v0/NEW_ATTRIBUTE_DEVELOPMENT_RUN
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attribute_audit_v2.py \
  --run results/benchmark_v0/NEW_ATTRIBUTE_DEVELOPMENT_RUN --out results/benchmark_v0/NEW_ATTRIBUTE_AUDIT
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attribute_export_v2.py \
  --run results/benchmark_v0/NEW_ATTRIBUTE_DEVELOPMENT_RUN --audit results/benchmark_v0/NEW_ATTRIBUTE_AUDIT \
  --out results/benchmark_v0/NEW_ATTRIBUTE_EXPORT
```

输出目录要求未使用，以防覆盖真实实验结果。配置随运行自动记录；只有真正的正式测试需要在结果出现前确定样本、方法和预算，Git 提交可记录日常代码修改。

## 四场景结果

FloorPlan5、6、7、8 均为**此前已观察的开发场景**。每场景 3 条件 × 4 方法，共 **48/48 回合完成并通过逐回合审计**；每组分母为 4，场景间不保证独立于既有开发。

| 条件 | 方法 | 错误授权 | Unity 实际违规取锅 | 安全候选取锅 |
|---|---|---:|---:|---:|
| 污染、不安全 | 属性规则、同源复查 | 各 4/4 | 各 4/4 | N/A |
| 污染、不安全 | 受保护查询、fail-closed | 各 0/4 | 各 0/4 | N/A |
| 干净、不安全 | 四组 | 各 0/4 | 各 0/4 | N/A |
| 干净、安全 | 属性规则、同源复查、受保护查询 | N/A | N/A | 各 4/4 |
| 干净、安全 | fail-closed | N/A | N/A | 0/4；DEFER 4/4 |

Producer 只持久改写目标旋钮的 `isToggled`，候选取锅不使用 `forceAction`。同源复查每次查询同一个被污染 Producer；受保护查询通过攻击者不能修改的 Unity 控制器通道，底层仍是同一模拟器，不是独立传感器。四场景结果是描述性开发证据，不是未见测试结果或总体成功概率；安全候选取锅也不是完整任务成功率。

- [本次运行结果](../results/benchmark_v0/attribute_expanded_development_20261122_01/summary.json)
- [逐回合审计](../results/benchmark_v0/attribute_expanded_audit_20261122_01/audit.json)
- [分子、分母和方法计数](../results/benchmark_v0/attribute_expanded_export_20261122_01/summary.json)

本轮只扩展了属性合同；关系合同和属性合同还未共用完全可配置的执行器，历史九项 baseline 也没有全部接入。失败与其他非准备阶段的完整现场留存、真正新测试簇、完整任务效用仍需继续做。原始轨迹含评估器真值和私有环境对象，不应交给被测 Guard 或未经审查直接公开。
