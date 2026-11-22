# Benchmark V0：监督执行、超时和中断验证

日期：2026-11-22。目标是在不改动历史冻结驱动及其结果的前提下，为开发套件补充案例进程级的超时、中断和状态保留机制。

## 本轮实现

新增 `scripts/benchmark_v0_supervised_suite_v2.py`，读取原冻结协议，逐案例调用现有原生驱动和独立审计。开始运行前写入案例级超时预算、冻结协议及监督器的哈希；状态文件使用临时文件和原子替换，输出目录和日志采用私有权限。每个案例记录 `NOT_STARTED`、`STARTED`、`AUDITED`、`TIMEOUT`、`FAILED`、`INTERRUPTED` 或 `AUDIT_MISSING` 等状态；非正常结果不会自动重试或覆盖旧运行。

子进程在新的进程组运行，超时或可捕获的中断会先发送终止信号，再对该组剩余进程强制结束。初版在进程组主进程退出后可能漏掉忽略终止信号的同组子进程；已保留初版作为历史记录，新版补充清理，并用专门的子进程测试验证。进程若自行脱离进程组、监督器被 SIGKILL 或机器断电，仍不能保证清理或写入最终状态；需要操作系统级资源管理或恢复机制来进一步覆盖。

**粒度限制：** 超时、失败和中断是案例进程级事件，不一定能定位到具体回合。旧驱动没有可靠的逐回合超时、方法不适用等状态输出，v2 离线转换器因此继续将缺失记录标记为 `UNKNOWN`，不会把案例级 TIMEOUT 直接赋予某一回合。未审计完成回合不进入当前的审计后指标分母。

## 本轮验证

1. **正常原生运行：** 使用已有 FloorPlan6 和 FloorPlan7 开发案例、原冻结 3×4 配置，修订版运行了 24 回合；两个案例各自的既有逐回合审计通过。结果转换为 24 条已完成且审计通过记录；12 个分组的安全指标与前一轮相同。这是重复性和运行入口检查，不是新的独立场景或模型实验。
2. **真实进程超时：** 人为设置每案例 `0.001` 秒，案例 1 记录 TIMEOUT，案例 2 记录 NOT_STARTED，程序以非零状态退出。原有逐回合转换器将 24 个缺失回合保守标记为 UNKNOWN，审计完成数为 0，避免把它们计入成功或失败。
3. **信号及故障测试：** 对真实监督器发送 SIGTERM 后验证状态持久化；另测试非零退出、零退出、无效超时、模拟中断，以及超时时终止忽略 SIGTERM 的同组子进程。相关 benchmark 测试 **24/24 通过**。

- 正常运行的案例级状态：`results/benchmark_v0/supervised_run_v2_20261122_01/status.json`
- 正常运行的逐回合与指标：`results/benchmark_v0/supervised_attempts_v2_20261122_01/summary.json`
- 人为超时的案例级状态：`results/benchmark_v0/supervised_timeout_v2_20261122_01/status.json`
- 人为超时的逐回合转换：`results/benchmark_v0/supervised_timeout_attempts_v2_20261122_01/summary.json`
- 单元与进程测试：`tests/test_benchmark_v0_supervised_v2.py`

原始正常运行目录含 evaluator 私有状态及日志，不应直接作为 Guard 输入或直接公开。已有案例审计重新检查了 Guard 重放、Producer 变更、Unity 回执及状态等，但本轮没有新增在线 Planner 调用，也不意味着完成未见场景泛化评估。

## 使用方法

输出必须为未使用的新目录。预算 `180` 秒是本轮每案例的监督超时，不是从状态消费到执行的 benchmark 时延。

```bash
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_supervised_suite_v2.py \
  --protocol results/benchmark_v0/suite_protocol_20261122_01/protocol.json \
  --out results/benchmark_v0/NEW_SUPERVISED_RUN --case-timeout-seconds 180
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/benchmark_v0_attempts_v2.py \
  --protocol results/benchmark_v0/suite_protocol_20261122_01/protocol.json \
  --run results/benchmark_v0/NEW_SUPERVISED_RUN --out results/benchmark_v0/NEW_ATTEMPTS
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m unittest discover -s tests -p 'test_benchmark_v0*.py' -v
```

下一步应设计新的逐回合运行协议，让实际开始、结束、超时、失败和不适用在回合级持久化；同时核验候选新场景的使用历史，在评估前冻结划分及案例生成规则。现有监督入口仍使用固定的四个 Guard 和单一关系合同。
