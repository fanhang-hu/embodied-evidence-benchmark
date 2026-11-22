# Benchmark V0：逐回合监督与超时验证

日期：2026-11-22。本轮在不修改历史冻结驱动的前提下，为固定候选开发套件增加逐回合观察、超时记录和标准结果导出。

## 做了什么

新增 `scripts/benchmark_v0_episode_supervisor_v1.py`。它按冻结的随机顺序预先登记每个案例的 12 个计划回合，轮询旧驱动的 `attempted/completed` 进度和逐回合记录，将观察到的开始、完成、未完成及超时事件写入原子替换的 `journal.json`；案例通过既有独立审计后，才将该案例已完成记录标记为审计通过。

逐回合超时从**监督器观察到开始**时计时，不是原生驱动内部精确开始时间。轮询可能延迟发现开始，极快的回合也可能没有观察到开始；有完成记录时仍能记录完成，但不能补造开始时间。超时后停止进程组并再次读取进度，只有最终进度仍明确指向被观察回合且没有完成记录时，才把它标为观察到的回合超时；否则保留未知。每案例总超时覆盖 Unity 启动与结束后的审计。

新增 `scripts/benchmark_v0_episode_journal_export_v1.py`，将监督日志与已审计原始记录结合为既有 v2 标准结果。仅在监督器正常记录了案例未启动时标记相关回合 `NOT_STARTED`；已启动案例中没有可靠结束证据的回合仍为 `UNKNOWN`。审计通过的已完成回合才计入安全指标，分组报告所有状态和实际分母。

这仍是对旧驱动的**外部观察层**，不是对驱动的原生逐回合插桩。旧驱动无法可靠细分失败、方法不适用等原因；被 SIGKILL、机器断电、进程自行脱离进程组时也不能保证最终记录或清理。日志和结果含评价信息，不得作为被测 Guard 输入或未经审查公开。

## 验证结果

- **正常原生运行：** 使用已观察过的 FloorPlan6、FloorPlan7 和既有 3 条件 × 4 Guard，24/24 回合产生完成记录，24/24 观察到开始，两个案例的逐回合审计均通过。标准导出的 12 组安全指标与前一轮一致。这只验证同一开发集的执行和记录，不是新场景或新模型结果。
- **真实短超时：** 人为把单回合观察后超时设为 0.01 秒；监督器记录 1 个 `TIMEOUT`，第一个已启动案例其余 11 回合为 `UNKNOWN`，尚未启动的第二案例 12 回合为 `NOT_STARTED`；审计完成数为 0，这些回合均不计入安全指标。0.01 秒只用于故障测试，不是合理的正式预算。
- **受控测试：** 验证了真实休眠子进程触发特定已观察回合超时、状态文件暂时无法解析时只报告案例超时、极快完成时不补造开始时间，以及案例标识不符时拒绝数据。相关 benchmark 测试 **28/28 通过**。

## 文件

- 正常运行逐回合日志：`results/benchmark_v0/episode_supervised_20261122_01/journal.json`
- 正常运行标准结果：`results/benchmark_v0/episode_supervised_export_20261122_01/summary.json`
- 故意超时日志：`results/benchmark_v0/episode_timeout_20261122_01/journal.json`
- 故意超时标准结果：`results/benchmark_v0/episode_timeout_export_20261122_01/summary.json`
- 测试：`tests/test_benchmark_v0_episode_supervisor_v1.py`

复现时使用尚不存在的新输出目录：

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_episode_supervisor_v1.py \
  --protocol results/benchmark_v0/suite_protocol_20261122_01/protocol.json \
  --out results/benchmark_v0/NEW_EPISODE_RUN --episode-timeout-seconds 60 --case-timeout-seconds 180
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_episode_journal_export_v1.py \
  --protocol results/benchmark_v0/suite_protocol_20261122_01/protocol.json \
  --run results/benchmark_v0/NEW_EPISODE_RUN --out results/benchmark_v0/NEW_EPISODE_EXPORT
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m unittest discover -s tests -p 'test_benchmark_v0*.py' -v
```

下一步应将逐回合状态写入真正可配置的新驱动，从源头记录准确的执行阶段、错误及不适用原因；并继续清点候选新场景的历史使用和可用性，先冻结划分与预算再执行评估。当前运行仍只有固定的四组 Guard 和关系合同。
