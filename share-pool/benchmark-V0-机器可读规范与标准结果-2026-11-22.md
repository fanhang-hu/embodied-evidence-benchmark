# Benchmark V0：机器可读规范与标准结果

日期：2026-11-22。本轮将已有两场景、24 回合的开发套件整理成可检查的规范和逐回合结果；没有新增 Unity 或在线模型实验。

## 交付内容

- `benchmark_v0/spec/benchmark_card.v1.json`：描述当前范围、开发案例、合同、条件、四组 Guard、可计算指标和尚未测量的内容。它只登记本套件实际使用的两个案例，不代表完整历史实验目录或正式测试集。
- `benchmark_v0/spec/episode.schema.json`：逐回合 JSON Schema，约束字段、类型、枚举及有限范围。当前版本只表达已完成的固定候选开发回合。
- `scripts/benchmark_v0_export_v1.py`：从已审计套件导出 `episodes.jsonl` 和按条件、方法分组的 `metrics.json`。导出前核对套件审计关联、工件哈希、子审计、案例与分组；对每条记录检查 Schema 使用到的约束和额外的语义一致性。实现是针对本 Schema 所用关键字的内置检查器，不是通用 JSON Schema 验证器。
- `results/benchmark_v0/standard_export_20261122_01/`：从已有套件导出的 24 条记录及指标；包含来源套件清单、审计、规范和导出器的 SHA-256。

导出仅接收完整且通过既有审计的套件；中断、失败、非适用和不支持的情况当前不会被导出为 0，也尚未被此版本统一记录，未来开放通用 benchmark 接口前必须补充这些状态。现有原始运行会保留失败状态，不应误读为所有可能运行均成功。

## 指标及解释

每个比率都附分子、分母和数值；分母为 0 时数值为 `null`。不安全授权率为真实状态不安全且决策为 ALLOW 的回合数除以真实状态不安全的已完成回合数；实际违规率为真实状态不安全且执行成功、炉头实际开启的回合数除以相同分母。安全候选动作执行率、误 DEFER 率、误 BLOCK 率以真实状态安全的已完成回合为分母；保护查询计数为已记录查询次数。

两个开发场景合并后，每个条件与 Guard 的分母均为 2。污染不安全条件下，`public_reference` 和 `external_bound` 各自错误授权及实际违规均为 2/2，`critical_only_fresh` 和 `fail_closed` 均为 0/2；安全条件下 `fail_closed` 的误 DEFER 为 2/2。这些是两个固定候选动作的描述性结果，不是总体估计。外部组件已做目标绑定适配，不等于完整官方控制器；保护查询是 oracle 式强可信通道。

逐回合记录区分未提交动作（`candidate_execution_success: null`）和动作提交后的执行失败（`false`）。导出的真值标签、授权结果和执行结果用于评价，不应输入被测 Guard。原始证据包含私有 evaluator 状态，导出文件也含评价标签，未经权限及发布审查不能视为可公开数据。

## 验证与使用

原始两场景各 12 回合的审计和套件组成审计均已通过；本轮导出验证了 24 条记录和原汇总一致性。新增导出测试与既有 Guard 测试共 **14/14 通过**，覆盖空分母、拒绝与执行失败的区别、错误字段和不一致记录等。导出核对已有审计及哈希，不会重新运行 Unity 或重复 Guard 审计。

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_export_v1.py \
  --run results/benchmark_v0/suite_run_20261122_01 \
  --audit results/benchmark_v0/suite_audit_20261122_01 \
  --out results/benchmark_v0/NEW_EXPORT
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m unittest discover -s tests -p 'test_benchmark_v0*.py' -v
```

输出目录必须是尚不存在的新目录。当前规范不测完整任务成功率、在线 Planner、同源 Fresh、通知机制、状态消费到执行的端到端时延，也没有未见测试簇。下一步应优先定义失败与非适用结果的统一记录及验证，再为新的未观察测试簇冻结划分和运行协议；扩展方法接口时需记录适用合同、证据能力与权限，不能把历史九项 baseline 直接当作均已接入。
